import json
import os
import re

from rank_bm25 import BM25Okapi

DATA_PATH = os.getenv(
    "DATA_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "articles.json"),
)

_articles: list[dict] = []
_bm25: BM25Okapi | None = None
_mtime: float = 0.0


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _load_index() -> None:
    global _articles, _bm25, _mtime
    try:
        mtime = os.path.getmtime(DATA_PATH)
    except FileNotFoundError:
        return
    if mtime == _mtime:
        return
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    _articles = data if isinstance(data, list) else data.get("articles", [])
    if not _articles:
        return
    corpus = [_tokenize(f"{a.get('title','')} {a.get('description','')}") for a in _articles]
    _bm25 = BM25Okapi(corpus)
    _mtime = mtime

def init_index() -> None:
    _load_index()

def filter_articles(query: str, limit: int = 50) -> list[dict]:
    _load_index()
    if _bm25 is None or not _articles:
        return []

    tokens = _tokenize(query)
    raw_scores = _bm25.get_scores(tokens)
    max_score = float(max(raw_scores)) if len(raw_scores) else 0.0

    results = []
    if max_score > 0:
        for article, raw in zip(_articles, raw_scores):
            score = round(float(raw) / max_score, 4)
            if score >= 0.1:
                results.append({**article, "score": score})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
