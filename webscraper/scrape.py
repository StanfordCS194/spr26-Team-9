import requests
from config import current_api, current_url
from apis import get_meta_description

QUERY = "Trump criticizes Pope Leo"
START = "2026-04-13T00:00:00Z"
END   = "2026-04-19T00:00:00Z"

def fetch_articles():
    res = requests.get(
        current_url,
        params={
            "keywords": QUERY,
            "language": "en",
            "page_size": 10,
            "start_date": START,
            "end_date": END,
            "apiKey": current_api,
        },
    )
    res.raise_for_status()
    return res.json().get("news", [])

def main():
    articles = fetch_articles()
    if not articles:
        print("No articles found.")
        return

    for article in articles:
        title = article.get("title", "No title")
        url   = article.get("url", "")
        date = article.get("published", "")
        author = article.get("author", "")
        desc  = get_meta_description(url) or article.get("description", "No description")

        print(f"Title: {title}")
        print(f"URL:   {url}")
        print(f"Desc:  {desc}")
        print(f"Date:   {date}")
        print(f"Author:   {author}")
        print("-" * 60)

if __name__ == "__main__":
    main()
