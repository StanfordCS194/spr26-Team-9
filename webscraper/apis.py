import requests
from bs4 import BeautifulSoup
from config import current_api, current_url


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
# Adapter
# ---------------------------------------------------------------------------

class CurrentAPIAdapter:
    def fetch(self, query, start, end, domain="foxnews.com"):
        res = requests.get(
            current_url,
            params={
                "keywords":   query,
                "language":   "en",
                "page_size":  10,
                "start_date": start,
                "end_date":   end,
                "apiKey":     current_api,
                "domain": domain
            },
        )
        res.raise_for_status()
        return [self._normalize(a) for a in res.json().get("news", [])]

    def _normalize(self, a):
        return {
            "title":       a.get("title", ""),
            "url":         a.get("url", ""),
            "description": a.get("description", ""),
            "date":        a.get("published", ""),
            "author":      a.get("author", ""),
        }


ADAPTERS = {
    "current": CurrentAPIAdapter,
}
