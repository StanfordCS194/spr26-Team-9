#!/usr/bin/env python3
"""
Refresh search cache for all suggested queries and write results to
data_public/search_cache/. Commit the updated files before deploying
so Render serves fresh articles without waiting for pre-warm.

Queries are refreshed sequentially so each call to refresh.py can use
its internal ThreadPoolExecutor to hit all three news APIs in parallel.

Usage:
    python webscraper/refresh_cache.py             # refresh + compute bias/stats
    python webscraper/refresh_cache.py --no-analysis  # skip bias/stats
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))

from search import filter_articles  # noqa: E402

SUGGESTED_QUERIES = [
    "Trump trade war tariffs",
    "Gaza ceasefire deal",
    "Trump Pope Leo",
]

CACHE_DIR = os.path.join(ROOT, "data_public", "search_cache")
PYTHON = shutil.which("python") or sys.executable


def _slug(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")


def refresh_query(query: str) -> None:
    print(f"\n{'='*60}")
    print(f"Refreshing: {query!r}")
    print(f"{'='*60}")

    subprocess.run(
        [PYTHON, os.path.join(HERE, "refresh.py"), "--query", query],
        check=True,
    )

    results = filter_articles(query)
    cached_at = time.time()

    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{_slug(query)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"query": query, "results": results, "cached_at": cached_at}, f, indent=2)

    print(f"Cached {len(results)} articles -> {os.path.relpath(path, ROOT)}")


def run_analysis() -> None:
    for script in ("compute_cache_bias.py", "text_source_stats.py"):
        path = os.path.join(ROOT, "data_analysis_nlp", script)
        print(f"\n{'='*60}")
        print(f"Running: data_analysis_nlp/{script}")
        print(f"{'='*60}")
        subprocess.run([PYTHON, path], check=True, cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh search cache for all suggested queries.")
    parser.add_argument(
        "--no-analysis",
        action="store_true",
        help="Skip bias computation and text source stats after refreshing.",
    )
    args = parser.parse_args()

    for query in SUGGESTED_QUERIES:
        try:
            refresh_query(query)
        except subprocess.CalledProcessError as exc:
            print(f"[error] Scraper failed for {query!r}: {exc}")

    if not args.no_analysis:
        try:
            run_analysis()
        except subprocess.CalledProcessError as exc:
            print(f"[error] Analysis failed: {exc}")

    print("\nDone. Commit data_public/ and push to deploy fresh cache to Render.")


if __name__ == "__main__":
    main()
