#!/usr/bin/env python3
"""
Refresh news articles about the Trump-Pope Leo feud.

Usage:
    python webscraper/refresh.py               # fetch from all APIs, merge into data/articles.json
    python webscraper/refresh.py --api newsapi # fetch from a single API only
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

PYTHON = shutil.which("python") or sys.executable
from datetime import datetime, timezone, timedelta

APIS      = ["newsapi", "nyt", "current"]
MAX_PAGES = 2

HERE     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
SCRAPER  = os.path.join(HERE, "scrape.py")

parser = argparse.ArgumentParser(description="Refresh news articles.")
parser.add_argument("--api", choices=APIS + ["all"], default="all")
parser.add_argument("--query", default="Trump Pope Leo")
args = parser.parse_args()

QUERY = args.query


def run_scraper(api, start, end):
    print(f"\n{'='*60}")
    print(f"Scraping {api.upper()} ...")
    print(f"{'='*60}")
    subprocess.run(
        [PYTHON, SCRAPER,
         "--query", QUERY,
         "--api", api,
         "--start", start,
         "--end", end,
         "--max-pages", str(MAX_PAGES),
         "--overwrite"],
        check=True,
    )


def is_relevant(article, keywords):
    """Return True if the article title or description mentions at least one keyword."""
    text = (article.get("title", "") + " " + article.get("description", "")).lower()
    return any(kw in text for kw in keywords)


def merge():
    keywords = [w.lower() for w in QUERY.split() if len(w) > 2]
    all_articles, seen = [], set()
    skipped = 0
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith("_articles.json"):
            continue
        with open(os.path.join(DATA_DIR, fname)) as f:
            for a in json.load(f):
                if a["url"] not in seen:
                    seen.add(a["url"])
                    if is_relevant(a, keywords):
                        all_articles.append(a)
                    else:
                        skipped += 1
    all_articles.sort(key=lambda a: a.get("date", ""), reverse=True)
    out = os.path.join(DATA_DIR, "articles.json")
    with open(out, "w") as f:
        json.dump(all_articles, f, indent=2)
    print(f"\nMerged {len(all_articles)} relevant articles ({skipped} off-topic removed) → {out}")


def main():
    now = datetime.now(timezone.utc)
    end   = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    start = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(DATA_DIR, exist_ok=True)

    apis_to_run = APIS if args.api == "all" else [args.api]
    for api in apis_to_run:
        try:
            run_scraper(api, start, end)
        except subprocess.CalledProcessError:
            print(f"\n[{api}] scrape failed — skipping.")

    merge()
    print("\nDone. Start the server with: python -m http.server 8080")
    print("Then open: http://localhost:8080/frontend/")


if __name__ == "__main__":
    main()
