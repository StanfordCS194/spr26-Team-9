import hashlib
import json
import math
import os

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel

router = APIRouter()

EMBEDDING_MODEL = "text-embedding-3-small"
SIMILARITY_THRESHOLD = 0.70
MAX_ARTICLES = 50
_cluster_cache: dict[str, list[list[int]]] = {}


class ClusterArticle(BaseModel):
    title: str
    description: str | None = ""


class SemanticClusterRequest(BaseModel):
    articles: list[ClusterArticle]


def _article_text(article: ClusterArticle) -> str:
    text = f"{article.title}. {article.description or ''}".strip()
    return text[:6000] or "Untitled article"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot_product = sum(x * y for x, y in zip(a, b))
    a_magnitude = math.sqrt(sum(x * x for x in a))
    b_magnitude = math.sqrt(sum(y * y for y in b))
    return dot_product / (a_magnitude * b_magnitude) if a_magnitude and b_magnitude else 0


def _cluster_embeddings(embeddings: list[list[float]]) -> list[list[int]]:
    clusters = [[article_index] for article_index in range(len(embeddings))]

    def average_similarity(a: list[int], b: list[int]) -> float:
        scores = [
            _cosine_similarity(embeddings[a_index], embeddings[b_index])
            for a_index in a
            for b_index in b
        ]
        return sum(scores) / len(scores)

    while len(clusters) > 1:
        best_pair = None
        best_score = 0.0
        for a_index in range(len(clusters)):
            for b_index in range(a_index + 1, len(clusters)):
                score = average_similarity(clusters[a_index], clusters[b_index])
                if score > best_score:
                    best_pair = (a_index, b_index)
                    best_score = score

        if best_pair is None or best_score < SIMILARITY_THRESHOLD:
            break

        a_index, b_index = best_pair
        clusters[a_index].extend(clusters[b_index])
        clusters.pop(b_index)

    return clusters


def _cache_key(articles: list[ClusterArticle]) -> str:
    payload = [{"title": article.title, "description": article.description} for article in articles]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


@router.post("/api/semantic-clusters")
async def semantic_clusters(req: SemanticClusterRequest):
    if not req.articles:
        return {"clusters": []}
    if len(req.articles) > MAX_ARTICLES:
        raise HTTPException(status_code=400, detail=f"Cluster up to {MAX_ARTICLES} articles.")

    key = _cache_key(req.articles)
    if key in _cluster_cache:
        return {"clusters": _cluster_cache[key], "cached": True}

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[_article_text(article) for article in req.articles],
            encoding_format="float",
        )
        embeddings = [item.embedding for item in response.data]
        clusters = _cluster_embeddings(embeddings)
        if len(_cluster_cache) >= 32:
            _cluster_cache.pop(next(iter(_cluster_cache)))
        _cluster_cache[key] = clusters
        return {"clusters": clusters, "cached": False}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
