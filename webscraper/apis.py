import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from config import current_api, current_url, news_api_key, news_api_url, nyt_api_key


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
    def fetch(self, query, start, end, **kwargs):
        # Currents API date filtering requires a paid plan; omit date params
        params = {
            "keywords": query,
            "language": "en",
            "page_size": 10,
            "apiKey": current_api,
        }
        if kwargs.get("domain", ""):
            params["domain"] = kwargs["domain"]
        res = requests.get(current_url, params=params)
        res.raise_for_status()
        return [self._normalize(a) for a in res.json().get("news", [])]

    def _normalize(self, a):
        # Convert "YYYY-MM-DD HH:MM:SS +HHMM" → ISO 8601 "YYYY-MM-DDTHH:MM:SS+HH:MM"
        raw_date = a.get("published", "")
        if raw_date:
            iso_date = re.sub(r" \+(\d{2})(\d{2})$", r"+\1:\2", raw_date.replace(" ", "T", 1))
        else:
            iso_date = ""
        return {
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "description": a.get("description", ""),
            "date": iso_date,
            "author": a.get("author", ""),
            "source": urlparse(a.get("url", "")).netloc.removeprefix("www."),
        }


class NYTAdapter:
    BASE_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"

    def fetch(self, query, start, end, **kwargs):
        """
        Args:
            query: keyword string
            start: ISO 8601 string (e.g. "2026-04-12T00:00:00Z")
            end:   ISO 8601 string
            page:  0-indexed page number (10 articles per page)
        Returns:
            List of normalized article dicts.
        """
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
                "api-key": nyt_api_key,
            },
            timeout=15,
        )
        res.raise_for_status()
        docs = res.json().get("response", {}).get("docs", [])
        return [self._normalize(d) for d in docs]

    def _normalize(self, d):
        return {
            "title":       d.get("headline", {}).get("main", ""),
            "url":         d.get("web_url", ""),
            "description": d.get("abstract", "") or d.get("snippet", ""),
            "date":        d.get("pub_date", ""),
            "author":      d.get("byline", {}).get("original", ""),
            "source":      "New York Times",
        }


class NewsAPIAdapter:
    def fetch(self, query, start, end, **kwargs):
        params = {
            "q": query,
            "from": start,
            "to": end,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "apiKey": news_api_key,
        }

        if kwargs.get("domain", ""):
            params["domains"] = kwargs.get("domain", "")

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