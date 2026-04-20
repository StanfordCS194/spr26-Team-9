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
                "api-key": NYT_API_KEY,
            },
            timeout=15,
        )
        res.raise_for_status()
        docs = res.json().get("response", {}).get("docs", [])
        return [self._normalize(d) for d in docs]

    def _normalize(self, d):
        headline = d.get("headline", {})
        multimedia = d.get("multimedia", {})
        return {
            # Core identity
            "nyt_id":          d.get("_id", ""),
            "url":             d.get("web_url", ""),
            "source":          d.get("source", ""),
            # Headlines
            "title":           headline.get("main", ""),
            "print_headline":  headline.get("print_headline", ""),
            # Text content
            "description":     d.get("abstract", "") or d.get("snippet", ""),
            # Metadata
            "date":            d.get("pub_date", ""),
            "author":          d.get("byline", {}).get("original", ""),
            "word_count":      d.get("word_count", 0),
            "document_type":   d.get("document_type", ""),
            "type_of_material": d.get("type_of_material", ""),
            # Editorial classification
            "news_desk":       d.get("news_desk", ""),
            "section":         d.get("section_name", ""),
            "subsection":      d.get("subsection_name", ""),
            "print_page":      d.get("print_page", ""),
            "print_section":   d.get("print_section", ""),
            # Keywords (list of {name, value, rank} dicts — useful for NLP)
            "keywords":        d.get("keywords", []),
            # Multimedia
            "image_url":       multimedia.get("default", {}).get("url", ""),
            "image_caption":   multimedia.get("caption", ""),
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