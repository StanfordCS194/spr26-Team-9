"""
Shared article text scraping utilities used across all bias experiments.

Provides get_article_text / resolve_text (extracted from fox_sentiment_bias.py)
and scrape_all, which maintains a URL-keyed JSON cache at data/scraped_text.json
so repeated runs skip already-fetched articles.

Cache format: {url: {text: str, text_source: "scraped"|"description"|"title"}}
"""

import json
import os

import trafilatura

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DEFAULT_CACHE_PATH = os.path.join(_DATA_DIR, "scraped_text.json")


def get_article_text(url: str) -> str | None:
    """Fetch and extract main article body using trafilatura."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            return trafilatura.extract(downloaded, include_comments=False)
    except Exception:
        pass
    return None


def resolve_text(article: dict) -> tuple[str, str]:
    """
    Return (text, source_label) for an article.
    Tries: scraped body → description → title.
    """
    text = get_article_text(article.get("url", ""))
    if text:
        return text, "scraped"
    desc = article.get("description") or ""
    if desc.strip():
        return desc, "description"
    return article.get("title", ""), "title"


def scrape_all(
    articles: list[dict],
    cache_path: str = DEFAULT_CACHE_PATH,
    verbose: bool = True,
) -> dict[str, dict]:
    """
    Scrape full text for all articles, maintaining a persistent URL-keyed cache.

    Returns the full cache dict: {url: {text, text_source}}.
    Only fetches articles not already in the cache.
    """
    cache: dict[str, dict] = {}
    if os.path.exists(cache_path):
        if verbose:
            print(f"Loading cached text from {cache_path}...")
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)

    to_scrape = [a for a in articles if a.get("url", "") not in cache]
    total = len(to_scrape)

    if total:
        if verbose:
            print(f"Scraping {total} uncached articles (already have {len(cache)})...")
        for i, article in enumerate(to_scrape, 1):
            url = article.get("url", "")
            if verbose:
                print(f"  {i}/{total}: {url[:80]}")
            text, src = resolve_text(article)
            cache[url] = {"text": text, "text_source": src}

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        if verbose:
            print(f"Saved {len(cache)} entries → {cache_path}")
    else:
        if verbose:
            print(f"All {len(articles)} articles already cached.")

    return cache
