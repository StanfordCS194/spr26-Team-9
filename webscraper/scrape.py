import json
import os
import time
from apis import ADAPTERS, get_meta_description

QUERY     = "Trump Pope Leo"
START     = "2026-04-12T00:00:00Z"
END       = "2026-04-19T00:00:00Z"
API       = "current"   # any key from ADAPTERS in apis.py. One of "current", "nytimes", "newsapi"
MAX_PAGES = 1       # 1 page = 10 articles; NYT rate limit: 5 req/min
DOMAIN = ""         # Specify a domain like foxnews.com, or bbc.co.uk. Leave as empty string for no specific domain.
OVERWRITE = False   # True: replace existing articles with freshly fetched data

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA_PATH = os.path.join(REPO_ROOT, "data", f"{API}_articles.json")


def load_existing(path):
    """Load previously saved articles, or return empty list."""
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []


def save(articles, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(articles, f, indent=2)


def main():
    adapter = ADAPTERS[API]()
    fetched = []

    for page in range(MAX_PAGES):
        fetched.extend(adapter.fetch(QUERY, START, END, page=page, domain=DOMAIN))
        if page < MAX_PAGES - 1:
            time.sleep(13)  # stay under 5 requests/minute (NYT limit)

    if not fetched:
        print("No articles found.")
        return

    for article in fetched:
        desc = get_meta_description(article["url"]) or article["description"] or "No description"
        print(f"Title:  {article['title']}")
        print(f"URL:    {article['url']}")
        print(f"Desc:   {desc}")
        print(f"Date:   {article['date']}")
        print(f"Author: {article['author']}")
        print("-" * 60)

    existing     = load_existing(DATA_PATH)
    fetched_urls = {a["url"] for a in fetched}

    if OVERWRITE:
        kept     = [a for a in existing if a["url"] not in fetched_urls]
        all_articles = kept + fetched
        print(f"\n[{API}] {len(fetched)} articles saved, "
              f"{len(existing) - len(kept)} overwritten "
              f"({len(all_articles)} total) → {DATA_PATH}")
    else:
        existing_urls = {a["url"] for a in existing}
        new_articles  = [a for a in fetched if a["url"] not in existing_urls]
        all_articles  = existing + new_articles
        print(f"\n[{API}] {len(new_articles)} new articles saved "
              f"({len(all_articles)} total) → {DATA_PATH}")

    save(all_articles, DATA_PATH)


if __name__ == "__main__":
    main()
