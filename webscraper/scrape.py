from apis import ADAPTERS, get_meta_description

QUERY = "Trump Pope Leo"
START = "2026-04-12T00:00:00Z"
END   = "2026-04-19T00:00:00Z"
API   = "current"


def main():
    adapter  = ADAPTERS[API]()
    articles = adapter.fetch(QUERY, START, END)

    if not articles:
        print("No articles found.")
        return

    for article in articles:
        desc = get_meta_description(article["url"]) or article["description"] or "No description"
        print(f"Title:  {article['title']}")
        print(f"URL:    {article['url']}")
        print(f"Desc:   {desc}")
        print(f"Date:   {article['date']}")
        print(f"Author: {article['author']}")
        print("-" * 60)


if __name__ == "__main__":
    main()
