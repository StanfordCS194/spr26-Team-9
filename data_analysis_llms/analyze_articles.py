import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
PROMPT_VERSION = "single_article_v1"
MAX_BODY_CHARS = 8_000

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ARTICLES_PATH = os.path.join(_DATA_DIR, "articles.json")
SCRAPED_TEXT_PATH = os.path.join(_DATA_DIR, "scraped_text.json")
LLM_ANALYSIS_PATH = os.path.join(_DATA_DIR, "llm_analysis.json")
LLM_RAW_PATH = os.path.join(_DATA_DIR, "llm_analysis_raw.json")

SINGLE_ARTICLE_ANALYSIS_PROMPT = """/no_think
You are analyzing one news article for a media narrative tracking product.

Your task is NOT to decide whether the article is good or bad.
Your task is to extract structured, evidence-grounded signals that help users compare this article with other coverage of the same story.

Return ONLY valid JSON.
Do not include markdown.
Do not include commentary outside the JSON.
Do not invent facts, quotes, sources, links, or perspectives.
If something is not present in the article, use null, [], or 0 as appropriate.
When quoting charged language or evidence, quote exact words from the article.
Be careful with "omitted perspectives": only identify them when they are strongly implied by the article topic and explain that they are "not present in this article", not that the outlet intentionally omitted them.

Output limits — include only the most important items up to each cap:
- key_claims: at most 5
- people_or_groups_mentioned: at most 10
- people_or_groups_quoted: at most 5
- people_or_groups_discussed_but_not_quoted: at most 5
- potentially_relevant_perspectives_not_present: at most 3
- charged_language: at most 5
- background_concepts: at most 4
- uncertainties_and_open_questions: at most 3
- what_to_compare_against_other_articles: at most 4

Analyze the article using this schema:

{{
  "schema_version": "1.0",

  "article_overview": {{
    "neutral_summary": "1-2 sentence neutral summary of the article",
    "main_topic": "short phrase describing the central topic",
    "article_type": "breaking_news | news_analysis | opinion | explainer | interview | investigative | video_segment | live_update | other | unclear",
    "event_stage": "initial_report | update | reaction | analysis | follow_up | retrospective | unclear",
    "main_update": "What new fact, claim, reaction, or interpretation this article appears to add, if any"
  }},

  "key_claims": [
    {{
      "claim": "A concise factual claim made by the article",
      "claim_type": "event | cause | consequence | accusation | response | statistic | prediction | interpretation | other",
      "attribution": "Who makes or supports this claim, e.g. reporter, named official, anonymous source, document, study, witness, unclear",
      "supporting_text": "Short exact quote or close paraphrase from the article supporting the claim",
      "certainty": "confirmed | alleged | disputed | speculative | unclear"
    }}
  ],

  "stakeholders": {{
    "people_or_groups_mentioned": [
      "Relevant people, groups, institutions, countries, companies, communities, etc."
    ],
    "people_or_groups_quoted": [
      {{
        "name_or_group": "Person or group quoted",
        "role": "Why they matter in the story",
        "position_or_view": "What viewpoint or information they contribute"
      }}
    ],
    "people_or_groups_discussed_but_not_quoted": [
      {{
        "name_or_group": "Person or group discussed but not directly quoted",
        "role": "Why they matter in the story"
      }}
    ],
    "potentially_relevant_perspectives_not_present": [
      {{
        "perspective": "A viewpoint or stakeholder that may be relevant but is not present in this article",
        "why_relevant": "Why this perspective might matter",
        "caution": "State that this is a possible missing perspective, not proof of bias"
      }}
    ]
  }},

  "evidence_signals": {{
    "reporter_or_byline_present": true,
    "named_sources_count": 0,
    "anonymous_sources_count": 0,
    "direct_quotes_count": 0,
    "mentions_documents_or_data": false,
    "mentions_studies_or_reports": false,
    "mentions_official_statements": false,
    "mentions_firsthand_witnesses": false,
    "links_or_references_primary_sources": false,
    "evidence_summary": "One sentence describing what kind of evidence the article mainly relies on"
  }},

  "framing_signals": {{
    "headline_frame": "How the headline frames the story, if headline is provided",
    "dominant_angle": "The main lens or angle of the article",
    "emphasized_aspects": [
      "Aspects of the story that receive the most attention"
    ],
    "deemphasized_aspects": [
      "Aspects that appear relevant but receive little attention"
    ],
    "causal_story": "What the article implies caused the event or situation, if any",
    "responsibility_assignment": "Who or what the article appears to assign responsibility to, if any",
    "tone": "neutral | urgent | skeptical | sympathetic | critical | alarmed | celebratory | uncertain | mixed",
    "tone_explanation": "Brief evidence-grounded explanation of the tone"
  }},

  "charged_language": [
    {{
      "phrase": "Exact phrase from the article",
      "reason": "Why this wording may affect the reader's interpretation",
      "intensity": "low | medium | high"
    }}
  ],

  "background_concepts": [
    {{
      "concept": "A concept, institution, event, law, policy, technical term, or historical reference readers may need to understand",
      "context": "Neutral 1-sentence explanation based only on general context and the article"
    }}
  ],

  "uncertainties_and_open_questions": [
    {{
      "question": "An important unresolved question raised by the article",
      "why_it_matters": "Why this uncertainty matters for interpreting the story"
    }}
  ],

  "comparison_ready_summary": {{
    "one_sentence_claim": "The article's main claim or takeaway in one sentence",
    "what_this_article_focuses_on": [
      "Focus area 1",
      "Focus area 2"
    ],
    "what_to_compare_against_other_articles": [
      "Claims, stakeholders, evidence, or framing choices that would be useful to compare across outlets"
    ]
  }}
}}

Article metadata:
Title: {title}
Source: {source}
Author: {author}
Published date: {published_at}
URL: {url}

Article text:
{body}
"""


def body_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def build_prompt(meta: dict, body: str) -> str:
    truncated = body[:MAX_BODY_CHARS]
    return SINGLE_ARTICLE_ANALYSIS_PROMPT.format(
        title=meta.get("title", ""),
        source=meta.get("source", ""),
        author=meta.get("author", ""),
        published_at=meta.get("date", ""),
        url=meta.get("url", ""),
        body=truncated,
    )


def call_nvidia_nim(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
        "temperature": 0.0,
    }
    response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def parse_json_response(raw: str) -> tuple[dict | None, str | None]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    try:
        return json.loads(cleaned), None
    except json.JSONDecodeError as e:
        return None, str(e)


def load_json_file(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json_file(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_cache_valid(entry: dict, current_prompt_version: str, current_body_hash: str) -> bool:
    return (
        entry.get("prompt_version") == current_prompt_version
        and entry.get("body_hash") == current_body_hash
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM analysis on scraped articles.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N articles")
    parser.add_argument("--dry-run", action="store_true", help="Print filled prompt for first article and exit")
    args = parser.parse_args()

    if not NVIDIA_API_KEY and not args.dry_run:
        raise RuntimeError("NVIDIA_API_KEY is not set in .env")

    print("Loading data...")
    articles: list[dict] = load_json_file(ARTICLES_PATH)
    scraped: dict[str, dict] = load_json_file(SCRAPED_TEXT_PATH)

    meta_by_url: dict[str, dict] = {a["url"]: a for a in articles if "url" in a}

    analysis_cache: dict[str, dict] = load_json_file(LLM_ANALYSIS_PATH)
    raw_cache: dict[str, dict] = load_json_file(LLM_RAW_PATH)

    urls = list(scraped.keys())
    if args.limit:
        urls = urls[: args.limit]

    if args.dry_run:
        url = urls[0]
        body = scraped[url].get("text", "")
        meta = meta_by_url.get(url, {"url": url})
        prompt = build_prompt(meta, body)
        print(f"\n{'='*60}")
        print(f"DRY RUN — URL: {url}")
        print(f"Body chars (truncated): {min(len(body), MAX_BODY_CHARS)}")
        print(f"{'='*60}\n")
        print(prompt)
        return

    skipped = 0
    processed = 0
    errors = 0

    print("Starting Analysis")

    for url in tqdm(urls, desc="Analyzing articles"):
        body = scraped[url].get("text", "")
        bhash = body_hash(body)
        meta = meta_by_url.get(url, {"url": url})

        existing = analysis_cache.get(url)
        if existing and is_cache_valid(existing, PROMPT_VERSION, bhash):
            skipped += 1
            continue

        prompt = build_prompt(meta, body)
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            raw = call_nvidia_nim(prompt)
        except Exception as e:
            tqdm.write(f"  API error for {url[:80]}: {e}")
            errors += 1
            time.sleep(2)
            continue

        raw_cache[url] = {
            "raw_response": raw,
            "prompt_version": PROMPT_VERSION,
            "body_hash": bhash,
            "timestamp": timestamp,
        }

        result, parse_error = parse_json_response(raw)

        analysis_cache[url] = {
            "url": url,
            "result": result,
            "parse_error": parse_error,
            "model": MODEL,
            "prompt_version": PROMPT_VERSION,
            "schema_version": "1.0",
            "body_hash": bhash,
            "timestamp": timestamp,
        }

        save_json_file(LLM_ANALYSIS_PATH, analysis_cache)
        save_json_file(LLM_RAW_PATH, raw_cache)

        status = "OK" if result else f"PARSE ERROR: {parse_error}"
        tqdm.write(f"  {url[:80]} → {status}")
        processed += 1
        time.sleep(1)

    print(f"\nDone. Processed: {processed}, Skipped (cached): {skipped}, Errors: {errors}")
    print(f"Results saved to {LLM_ANALYSIS_PATH}")


if __name__ == "__main__":
    main()
