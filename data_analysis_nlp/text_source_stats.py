"""
Scrape full text for all search-cached articles, then print per-source and
per-API statistics showing how many articles resolved via full scrape,
description, or title fallback.

Run from repo root:
    python data_analysis_nlp/text_source_stats.py
"""

import glob
import json
import os
import sys
from collections import defaultdict

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_DIR, "..")
sys.path.insert(0, _ROOT)

SEARCH_CACHE_DIR  = os.path.join(_ROOT, "data_public", "search_cache")
SCRAPED_TEXT_PATH = os.path.join(_ROOT, "data", "scraped_text.json")
DATA_DIR          = os.path.join(_ROOT, "data")

API_FILES = {
    "nyt":     "nyt_articles.json",
    "newsapi": "newsapi_articles.json",
    "currents": "current_articles.json",
}

SOURCE_ORDER = ("scraped", "description", "title")


def build_api_lookup() -> dict[str, str]:
    """Build url -> api_name from per-API article files for best-effort tagging."""
    lookup: dict[str, str] = {}
    for api_name, fname in API_FILES.items():
        path = os.path.join(DATA_DIR, fname)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            articles = json.load(f)
        for a in articles:
            url = a.get("url", "")
            if url:
                lookup[url] = api_name
    return lookup


def load_cache_articles() -> list[dict]:
    articles_by_url: dict[str, dict] = {}
    pattern = os.path.join(SEARCH_CACHE_DIR, "*.json")
    for path in sorted(glob.glob(pattern)):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for article in data.get("results", []):
            url = article.get("url", "")
            if url and url not in articles_by_url:
                articles_by_url[url] = article
    return list(articles_by_url.values())


def print_stats(articles: list[dict], text_cache: dict[str, dict], api_lookup: dict[str, str]) -> None:
    overall: dict[str, int] = defaultdict(int)
    overall_chars: list[int] = []
    per_source: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_source_chars: dict[str, list[int]] = defaultdict(list)
    per_api: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_api_chars: dict[str, list[int]] = defaultdict(list)

    for article in articles:
        url = article.get("url", "")
        source = article.get("source", "unknown")
        api = article.get("api") or api_lookup.get(url, "unknown")
        entry = text_cache.get(url, {})
        text_src = entry.get("text_source", "missing")
        char_count = len(entry.get("text") or "")

        overall[text_src] += 1
        overall_chars.append(char_count)
        per_source[source][text_src] += 1
        per_source_chars[source].append(char_count)
        per_api[api][text_src] += 1
        per_api_chars[api].append(char_count)

    total = len(articles)
    avg_all = sum(overall_chars) / len(overall_chars) if overall_chars else 0

    # --- Overall ---
    print(f"\n{'='*60}")
    print(f"OVERALL  ({total} articles, avg {avg_all:,.0f} chars)")
    print(f"{'='*60}")
    for label in SOURCE_ORDER:
        n = overall.get(label, 0)
        print(f"  {label:<12} {n:>3}  {'#' * n}")
    if overall.get("missing"):
        print(f"  {'missing':<12} {overall['missing']:>3}  (not yet scraped)")

    # --- Per API ---
    print(f"\n{'='*60}")
    print("PER API")
    print(f"{'='*60}")
    api_col = max((len(a) for a in per_api), default=8) + 2
    _print_table(per_api, per_api_chars, api_col)

    # --- Per source ---
    print(f"\n{'='*60}")
    print("PER SOURCE")
    print(f"{'='*60}")
    src_col = max((len(s) for s in per_source), default=8) + 2
    _print_table(per_source, per_source_chars, src_col)


def _print_table(groups: dict, char_lists: dict[str, list[int]], col_w: int) -> None:
    header = (
        f"{'NAME':<{col_w}}  {'SCRAPED':>8}  {'DESCRIPTION':>12}"
        f"  {'TITLE':>6}  {'TOTAL':>6}  {'AVG CHARS':>10}"
    )
    print(header)
    print("-" * len(header))
    for name in sorted(groups, key=lambda s: -sum(groups[s].values())):
        counts = groups[name]
        chars = char_lists.get(name, [])
        avg = sum(chars) / len(chars) if chars else 0
        row_total = sum(counts.values())
        print(
            f"{name:<{col_w}}"
            f"  {counts.get('scraped', 0):>8}"
            f"  {counts.get('description', 0):>12}"
            f"  {counts.get('title', 0):>6}"
            f"  {row_total:>6}"
            f"  {avg:>10,.0f}"
        )


def main() -> None:
    articles = load_cache_articles()
    if not articles:
        sys.exit(f"No articles found in {SEARCH_CACHE_DIR}")
    print(f"Loaded {len(articles)} unique articles from search cache.")

    api_lookup = build_api_lookup()
    tagged = sum(1 for a in articles if a.get("api") or api_lookup.get(a.get("url", "")))
    print(f"API origin known for {tagged}/{len(articles)} articles "
          f"({'new adapter field' if any(a.get('api') for a in articles) else 'fallback file lookup'}).")

    from webscraper.text_utils import scrape_all
    text_cache = scrape_all(articles, cache_path=SCRAPED_TEXT_PATH)

    print_stats(articles, text_cache, api_lookup)


if __name__ == "__main__":
    main()
