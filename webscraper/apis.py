import requests
from bs4 import BeautifulSoup


def get_meta_description(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Try og:description first (usually longer), fallback to meta description
        og = soup.find("meta", property="og:description")
        if og and og.get("content"):
            return og["content"]
        
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"]
        
        return None
    except Exception as e:
        return f"[Error: {e}]"