"""
Compute bias labels for articles in the search cache that do not yet have them.

Reads all articles from data_public/search_cache/*.json, scrapes full text
(cached at data/scraped_text.json), runs politicalBiasBERT on any article
missing a bias label, and merges the results into data_public/bias_all_articles.json.

Run from repo root:
    python data_analysis_nlp/compute_cache_bias.py
"""

import glob
import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_DIR, "..")
sys.path.insert(0, _ROOT)

SEARCH_CACHE_DIR  = os.path.join(_ROOT, "data_public", "search_cache")
SCRAPED_TEXT_PATH = os.path.join(_ROOT, "data", "scraped_text.json")
BIAS_PATH         = os.path.join(_ROOT, "data_public", "bias_all_articles.json")


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


def load_existing_bias() -> dict[str, dict]:
    if not os.path.exists(BIAS_PATH):
        return {}
    with open(BIAS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    articles = load_cache_articles()
    if not articles:
        sys.exit(f"No articles found in {SEARCH_CACHE_DIR}")
    print(f"Found {len(articles)} unique articles across search cache files.")

    existing = load_existing_bias()

    # Include any existing bias entry that is missing the current (full-distribution)
    # scores as a stub article so it gets re-scored. These are orphans left over
    # from earlier, larger search caches; without this they keep their stale,
    # old-method scores and the file ends up mixing two scoring methods.
    cache_urls = {a.get("url", "") for a in articles}
    orphan_stubs = [
        {"url": url, "source": rec.get("source", "unknown")}
        for url, rec in existing.items()
        if url not in cache_urls and "prob_right" not in rec
    ]
    if orphan_stubs:
        print(f"Found {len(orphan_stubs)} orphan entries needing re-scoring (not in current cache).")
        articles = articles + orphan_stubs

    new_count = sum(1 for a in articles if a.get("url", "") not in existing)
    legacy_count = sum(
        1 for a in articles
        if a.get("url", "") in existing and "prob_right" not in existing[a["url"]]
    )
    print(
        f"Existing bias labels: {len(existing)}  |  "
        f"New: {new_count}  |  Legacy to upgrade: {legacy_count}"
    )

    from webscraper.text_utils import scrape_all
    text_cache = scrape_all(articles, cache_path=SCRAPED_TEXT_PATH)

    from data_analysis_nlp.bias_by_source import run_bias_pipeline
    results = run_bias_pipeline(articles, text_cache, cached=existing)

    merged = {**existing, **results}
    with open(BIAS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(merged)} bias entries -> {BIAS_PATH}")
    print(f"  Added: {len(merged) - len(existing)}  |  Already had: {len(existing)}")


if __name__ == "__main__":
    main()
