import json
import os
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

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
FRONTEND_DIR = os.path.join(HERE, "..", "frontend")
PYTHON = shutil.which("python") or sys.executable

SUGGESTED_QUERIES = [
    "Trump trade war tariffs",
    "Gaza ceasefire deal",
    "AI regulation Congress",
]
_SUGGESTED_LOWER = {q.lower() for q in SUGGESTED_QUERIES}

CACHE_TTL = 86400  # 24 hours

_search_cache: dict[str, dict] = {}  # normalized_query -> {results, cached_at}
_scraper_lock = threading.Lock()


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
        _search_cache[query.strip().lower()] = {"results": results, "cached_at": time.time()}

    return results


def _prewarm_worker():
    """Background thread: sequentially pre-warm cache for all suggested queries."""
    for query in SUGGESTED_QUERIES:
        key = query.lower()
        cached = _search_cache.get(key)
        if cached and (time.time() - cached["cached_at"]) < CACHE_TTL:
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

@app.get("/api/ready")
def api_ready():
    return {"ready": True}


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

    if os.path.isdir(DATA_DIR):
        for fname in os.listdir(DATA_DIR):
            if fname.endswith("_articles.json"):
                os.remove(os.path.join(DATA_DIR, fname))

    try:
        proc = subprocess.run(
            [PYTHON, os.path.join(HERE, "..", "webscraper", "refresh.py"), "--query", query],
            check=True,
            timeout=180,
            capture_output=True,
            text=True,
        )
        print(proc.stdout)
        print(proc.stderr)
    except subprocess.CalledProcessError as e:
        print(e.stdout)
        print(e.stderr)
        raise HTTPException(status_code=500, detail=e.stderr or str(e)) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Scraping timed out") from e

    results = filter_articles(query)
    return {"query": query, "results": results}


if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")