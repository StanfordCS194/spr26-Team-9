import requests
from bs4 import BeautifulSoup
from config import current_api, current_url, news_api_key, news_api_url
from api_keys import NYT_API_KEY


# ---------------------------------------------------------------------------
# Shared utility
# ---------------------------------------------------------------------------

def get_meta_description(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        og = soup.find("meta", property="og:description")
        if og and og.get("content"):
            return og["content"]

        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"]

        return None
    except Exception as e:
        return f"[Error: {e}]"


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

class CurrentAPIAdapter:
    def fetch(self, query, start, end, domain="foxnews.com"):
        res = requests.get(
            current_url,
            params={
                "keywords": query,
                "language": "en",
                "page_size": 10,
                "start_date": start,
                "end_date": end,
                "apiKey": current_api,
                "domain": domain,
            },
        )
        res.raise_for_status()
        return [self._normalize(a) for a in res.json().get("news", [])]

    def _normalize(self, a):
        return {
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "description": a.get("description", ""),
            "date": a.get("published", ""),
            "author": a.get("author", ""),
        }


class NYTAdapter:
    BASE_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"

    def fetch(self, query, start, end, **kwargs):
        begin_date = start[:10].replace("-", "")
        end_date = end[:10].replace("-", "")

        res = requests.get(
            self.BASE_URL,
            params={
                "q": query,
                "begin_date": begin_date,
                "end_date": end_date,
                "sort": "oldest",
                "page": kwargs.get("page", 0),
                "api-key": NYT_API_KEY,
            },
            timeout=15,
        )
        res.raise_for_status()
        docs = res.json().get("response", {}).get("docs", [])
        return [self._normalize(d) for d in docs]

    def _normalize(self, d):
        return {
            "title": d.get("headline", {}).get("main", ""),
            "url": d.get("web_url", ""),
            "description": d.get("abstract", "") or d.get("snippet", ""),
            "lead_paragraph": d.get("lead_paragraph", ""),
            "date": d.get("pub_date", ""),
            "author": d.get("byline", {}).get("original", ""),
        }


class NewsAPIAdapter:
    def fetch(self, query, start, end, domain=None):
        params = {
            "q": query,
            "from": start,
            "to": end,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "apiKey": news_api_key,
        }

        if domain:
            params["domains"] = domain

        res = requests.get(news_api_url, params=params, timeout=15)
        res.raise_for_status()

        return [self._normalize(a) for a in res.json().get("articles", [])]

    def _normalize(self, a):
        return {
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "description": a.get("description", ""),
            "date": a.get("publishedAt", ""),
            "author": a.get("author", ""),
            "source": a.get("source", {}).get("name", "NewsAPI"),
        }


ADAPTERS = {
    "current": CurrentAPIAdapter,
    "nyt": NYTAdapter,
    "newsapi": NewsAPIAdapter,
}