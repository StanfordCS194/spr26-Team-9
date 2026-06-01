import concurrent.futures
import json
import os
import re
from datetime import datetime, timedelta, timezone

import anthropic
from fastapi import APIRouter, HTTPException, Query
from google import genai
from google.genai import types as genai_types
from openai import OpenAI

router = APIRouter()

LLM_CONFIGS = [
    {"name": "ChatGPT", "color": "#10a37f", "model": "gpt-5.4-mini"},
    {"name": "Gemini",  "color": "#4285f4", "model": "gemini-3.5-flash"},
    {"name": "Claude",  "color": "#cc785c", "model": "claude-haiku-4-5"},
]

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "..", "data", "llm_summaries")
CACHE_TTL_HOURS = 24

_SUMMARY_PROMPT = "Summarize the latest news about: {query}. Cite your sources with URLs."

_ANALYSIS_SYSTEM = (
    "You are an analyst extracting structured data from an AI chatbot's news response. "
    "Return valid JSON only with exactly these keys:\n"
    '- "summary": string, 2-3 sentences characterizing how this LLM told the story '
    "(neutral meta-analysis of framing, not a re-summary of events)\n"
    '- "biases": array of {{"title": string, "body": string}}, 2-4 specific bias findings '
    "(framing bias, omission bias, source bias, etc.)\n"
    '- "sources": array of {{"label": string, "url": string}}, every URL cited in the response '
    'formatted as "domain.com — anchor text"\n'
    "Do not include any text outside the JSON object."
)


def _slug(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")


def _cache_path(query: str) -> str:
    return os.path.join(CACHE_DIR, f"{_slug(query)}.json")


def _load_cache(query: str) -> dict | None:
    path = _cache_path(query)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        generated_at = datetime.fromisoformat(data["generated_at"])
        if datetime.now(timezone.utc) - generated_at > timedelta(hours=CACHE_TTL_HOURS):
            return None
        return data
    except Exception:
        return None


def _write_cache(data: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(data["query"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


# ── Step 1: web-grounded queries ───────────────────────────

def _query_openai(query: str, model: str) -> str:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.responses.create(
        model=model,
        tools=[{"type": "web_search_preview"}],
        input=_SUMMARY_PROMPT.format(query=query),
    )
    return resp.output_text


def _query_gemini(query: str, model: str) -> str:
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    resp = client.models.generate_content(
        model=model,
        contents=_SUMMARY_PROMPT.format(query=query),
        config=genai_types.GenerateContentConfig(
            tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
        ),
    )
    return resp.text


def _query_claude(query: str, model: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": _SUMMARY_PROMPT.format(query=query)}],
    )
    return "\n\n".join(block.text for block in resp.content if hasattr(block, "text"))


# ── Step 2: meta-analysis using the same model ─────────────

def _analyze_openai(query: str, raw: str, model: str) -> dict:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _ANALYSIS_SYSTEM},
            {"role": "user", "content": f"News topic: {query}\n\nLLM response to analyze:\n{raw}"},
        ],
        temperature=0.2,
    )
    return json.loads(resp.choices[0].message.content)


def _analyze_gemini(query: str, raw: str, model: str) -> dict:
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    resp = client.models.generate_content(
        model=model,
        contents=f"{_ANALYSIS_SYSTEM}\n\nNews topic: {query}\n\nLLM response to analyze:\n{raw}",
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return _extract_json(resp.text)


def _analyze_claude(query: str, raw: str, model: str) -> dict:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_ANALYSIS_SYSTEM,
        messages=[{"role": "user", "content": f"News topic: {query}\n\nLLM response to analyze:\n{raw}"}],
    )
    text = "\n\n".join(block.text for block in resp.content if hasattr(block, "text"))
    return _extract_json(text)


_QUERY_FN    = {"ChatGPT": _query_openai,   "Gemini": _query_gemini,   "Claude": _query_claude}
_ANALYZE_FN  = {"ChatGPT": _analyze_openai, "Gemini": _analyze_gemini, "Claude": _analyze_claude}


def _process_llm(cfg: dict, query: str) -> dict:
    raw_response = _QUERY_FN[cfg["name"]](query, cfg["model"])
    extracted    = _ANALYZE_FN[cfg["name"]](query, raw_response, cfg["model"])
    return {
        "name":         cfg["name"],
        "model":        cfg["model"],
        "color":        cfg["color"],
        "raw_response": raw_response,
        "summary":      extracted.get("summary", ""),
        "biases":       extracted.get("biases", []),
        "sources":      extracted.get("sources", []),
    }


def _run_pipeline(query: str) -> dict:
    order = {cfg["name"]: i for i, cfg in enumerate(LLM_CONFIGS)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(LLM_CONFIGS)) as pool:
        futures = {pool.submit(_process_llm, cfg, query): cfg for cfg in LLM_CONFIGS}
        llm_results = [f.result() for f in concurrent.futures.as_completed(futures)]
    llm_results.sort(key=lambda x: order.get(x["name"], 99))

    result = {
        "query":        query,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "llms":         llm_results,
    }
    _write_cache(result)
    return result


@router.get("/api/llm-summary")
async def get_llm_summary(q: str = Query(..., min_length=1)):
    query = q.strip()
    cached = _load_cache(query)
    if cached:
        return cached
    try:
        return _run_pipeline(query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
