import argparse
import json
import os
import time
from apis import ADAPTERS, get_meta_description

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


def load_existing(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read().strip()
            if content:
                return json.loads(content)
    return []


def save(articles, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(articles, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Scrape news articles.")
    parser.add_argument("--query",     default="Trump Pope Leo")
    parser.add_argument("--api",       default="newsapi", choices=list(ADAPTERS.keys()))
    parser.add_argument("--start",     default="2026-04-12T00:00:00Z")
    parser.add_argument("--end",       default="2026-04-27T00:00:00Z")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--domain",    default="")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    data_path = os.path.join(REPO_ROOT, "data", f"{args.api}_articles.json")

    adapter = ADAPTERS[args.api]()
    fetched = []

    for page in range(args.max_pages):
        fetched.extend(adapter.fetch(args.query, args.start, args.end, page=page, domain=args.domain))
        if page < args.max_pages - 1:
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

    existing     = load_existing(data_path)
    fetched_urls = {a["url"] for a in fetched}

    if args.overwrite:
        kept         = [a for a in existing if a["url"] not in fetched_urls]
        all_articles = kept + fetched
        print(f"\n[{args.api}] {len(fetched)} articles saved, "
              f"{len(existing) - len(kept)} overwritten "
              f"({len(all_articles)} total) → {data_path}")
    else:
        existing_urls = {a["url"] for a in existing}
        new_articles  = [a for a in fetched if a["url"] not in existing_urls]
        all_articles  = existing + new_articles
        print(f"\n[{args.api}] {len(new_articles)} new articles saved "
              f"({len(all_articles)} total) → {data_path}")

    save(all_articles, data_path)


if __name__ == "__main__":
    main()
