import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from search import filter_articles
from users import router as users_router
from compare import router as compare_router
from bias import router as bias_router
from channel_summary import router as channel_summary_router
from llm_summary import router as llm_summary_router

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
CACHE_DIR = os.path.join(HERE, "..", "data_public", "search_cache")
FRONTEND_DIR = os.path.join(HERE, "..", "frontend")
PYTHON = shutil.which("python") or sys.executable

SUGGESTED_QUERIES = [
    "Trump trade war tariffs",
    "Gaza ceasefire deal",
    "Trump Pope Leo",
]
_SUGGESTED_LOWER = {q.lower() for q in SUGGESTED_QUERIES}

_search_cache: dict[str, dict] = {}  # normalized_query -> {results, cached_at}
_scraper_lock = threading.Lock()


def _slug(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")


def _save_cache_to_disk(query: str, results: list[dict], cached_at: float) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{_slug(query)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"query": query, "results": results, "cached_at": cached_at}, f)


def _load_cache_from_disk() -> None:
    if not os.path.isdir(CACHE_DIR):
        return
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(CACHE_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            key = data["query"].strip().lower()
            if key in _SUGGESTED_LOWER:
                _search_cache[key] = {"results": data["results"], "cached_at": data["cached_at"]}
                print(f"[cache] Loaded from disk: {data['query']!r}")
        except Exception as exc:
            print(f"[cache] Failed to load {fname}: {exc}")


def _run_scraper_and_cache(query: str) -> list[dict]:
    """Run webscraper for query, store in cache if it's a suggested query, and return results."""
    if os.path.isdir(DATA_DIR):
        for fname in os.listdir(DATA_DIR):
            if fname.endswith("_articles.json"):
                os.remove(os.path.join(DATA_DIR, fname))

    proc = subprocess.run(
        [PYTHON, os.path.join(HERE, "..", "webscraper", "refresh.py"), "--query", query],
        check=True,
        timeout=180,
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    print(proc.stderr)

    results = filter_articles(query)

    if query.strip().lower() in _SUGGESTED_LOWER:
        cached_at = time.time()
        _search_cache[query.strip().lower()] = {"results": results, "cached_at": cached_at}
        _save_cache_to_disk(query, results, cached_at)

    return results


def _prewarm_worker():
    """Background thread: sequentially pre-warm cache for all suggested queries."""
    for query in SUGGESTED_QUERIES:
        key = query.lower()
        cached = _search_cache.get(key)
        if cached:
            continue
        try:
            print(f"[prewarm] Starting cache warm for: {query!r}")
            with _scraper_lock:
                _run_scraper_and_cache(query)
            print(f"[prewarm] Done: {query!r}")
        except Exception as exc:
            print(f"[prewarm] Failed for {query!r}: {exc}")


app = FastAPI(title="News Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
app.include_router(compare_router)
app.include_router(bias_router)
app.include_router(channel_summary_router)
app.include_router(llm_summary_router)

@app.on_event("startup")
async def prewarm_cache():
    _load_cache_from_disk()
    t = threading.Thread(target=_prewarm_worker, daemon=True)
    t.start()


@app.get("/api/ready")
def api_ready():
    return {"ready": True}


@app.get("/api/suggestions")
def api_suggestions():
    return {"suggestions": SUGGESTED_QUERIES}


@app.get("/data/{filename:path}")
def data_files(filename: str):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


@app.get("/api/progress")
def api_progress():
    apis = ["newsapi", "nyt", "current"]
    done = sum(
        1 for api in apis
        if os.path.isfile(os.path.join(DATA_DIR, f"{api}_articles.json"))
    )
    merged = os.path.isfile(os.path.join(DATA_DIR, "articles.json"))
    return {"done": done, "total": len(apis), "merged": merged}


@app.get("/api/articles")
def api_articles():
    path = os.path.join(DATA_DIR, "articles.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="articles.json not found")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="No query provided")

    key = query.lower()

    def _cache_hit():
        if key not in _SUGGESTED_LOWER:
            return None
        cached = _search_cache.get(key)
        if cached:
            return cached["results"]
        return None

    results = _cache_hit()
    if results is not None:
        return {"query": query, "results": results}

    try:
        with _scraper_lock:
            # Re-check after acquiring lock — pre-warm may have just finished
            results = _cache_hit()
            if results is not None:
                return {"query": query, "results": results}
            results = _run_scraper_and_cache(query)
    except subprocess.CalledProcessError as e:
        print(e.stdout)
        print(e.stderr)
        raise HTTPException(
            status_code=502,
            detail="Some news sources could not be reached. Please try the search again.",
        ) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(
            status_code=504,
            detail="The news search took too long. Please try again.",
        ) from e

    return {"query": query, "results": results}


if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
