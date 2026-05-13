"""
Cluster articles from data/articles.json into sub-events (stories) using
sentence-transformer embeddings + HDBSCAN.

Encodes full article body text (scraped → description → title fallback) so that
the embedding space here matches source_bias_clustering.py exactly. Story
centroids and framing residuals computed downstream are therefore consistent
with the cluster assignments made here.

Embeddings are cached to data/article_embeddings.json so source_bias_clustering.py
can reuse them without re-encoding.

story_id == -1 (HDBSCAN noise) means the article's coverage is too sparse or
isolated to compare framing — these are surfaced in the summary rather than dropped,
since opinion/analysis pieces frequently land here.

Outputs:
  data/scraped_text.json      — full-text cache (for downstream pipelines)
  data/article_embeddings.json — {url: embedding} cache reused by source_bias_clustering
  data/stories.json            — {url: story_id} for all articles

Run from repo root: python experiments/story_clustering.py
"""

import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

ARTICLES_PATH    = os.path.join(_DIR, "..", "data", "articles.json")
STORIES_PATH     = os.path.join(_DIR, "..", "data", "stories.json")
EMBEDDINGS_PATH  = os.path.join(_DIR, "..", "data", "article_embeddings.json")


def main() -> None:
    try:
        from sentence_transformers import SentenceTransformer
        import hdbscan
    except ImportError as e:
        sys.exit(
            f"Missing dependency: {e}\n"
            "Install with: pip install sentence-transformers hdbscan"
        )

    from experiments.text_utils import scrape_all

    with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
        articles = json.load(f)
    print(f"Loaded {len(articles)} articles from {ARTICLES_PATH}")

    # Scrape full text — downstream scripts need this cache too
    text_cache = scrape_all(articles)

    # Resolve the same text each article will use in source_bias_clustering
    texts = []
    for a in articles:
        entry = text_cache.get(a.get("url", ""), {})
        texts.append(entry.get("text") or a.get("description") or a.get("title", ""))

    print("Loading sentence-transformer model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Load or compute embeddings
    if os.path.exists(EMBEDDINGS_PATH):
        print(f"Loading cached embeddings from {EMBEDDINGS_PATH}...")
        with open(EMBEDDINGS_PATH, "r", encoding="utf-8") as f:
            emb_cache = json.load(f)
        cached_urls = {a.get("url", "") for a in articles if a.get("url", "") in emb_cache}
        if len(cached_urls) == len(articles):
            embeddings = np.array([emb_cache[a.get("url", "")] for a in articles], dtype=np.float32)
        else:
            print(f"Cache incomplete ({len(cached_urls)}/{len(articles)}), re-encoding...")
            embeddings = None
    else:
        emb_cache = {}
        embeddings = None

    if embeddings is None:
        print(f"Encoding {len(texts)} article bodies...")
        embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)
        emb_cache = {a.get("url", ""): emb.tolist() for a, emb in zip(articles, embeddings)}
        with open(EMBEDDINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(emb_cache, f, ensure_ascii=False)
        print(f"Saved embeddings → {EMBEDDINGS_PATH}")

    print("Clustering with HDBSCAN(min_cluster_size=3)...")
    clusterer = hdbscan.HDBSCAN(min_cluster_size=3, metric="euclidean")
    story_ids = clusterer.fit_predict(embeddings).tolist()

    stories = {a.get("url", ""): sid for a, sid in zip(articles, story_ids)}
    with open(STORIES_PATH, "w", encoding="utf-8") as f:
        json.dump(stories, f, indent=2, ensure_ascii=False)
    print(f"Saved story assignments → {STORIES_PATH}")

    # Summary
    counts = Counter(story_ids)
    n_noise = counts.get(-1, 0)
    n_clusters = sum(1 for k in counts if k >= 0)
    print(f"\nClusters: {n_clusters}  |  Noise articles: {n_noise}/{len(articles)}")

    src_by_story: dict[int, set] = defaultdict(set)
    for article, sid in zip(articles, story_ids):
        if sid >= 0:
            src_by_story[sid].add(article.get("source", "unknown"))

    for sid in sorted(src_by_story):
        srcs = sorted(src_by_story[sid])
        n_arts = counts[sid]
        src_preview = ", ".join(srcs[:6]) + ("…" if len(srcs) > 6 else "")
        print(f"  Story {sid}: {n_arts} articles, {len(srcs)} sources — {src_preview}")

    if n_noise:
        noise_articles = [a for a, sid in zip(articles, story_ids) if sid == -1]
        noise_srcs = Counter(a.get("source", "unknown") for a in noise_articles)
        print(f"\nNoise articles by source: {dict(noise_srcs.most_common(10))}")
        print(
            "  Note: noise articles are excluded from framing analysis — no shared "
            "story means no meaningful centroid to subtract from. They're preserved "
            "in stories.json so callers can inspect or surface them separately."
        )


if __name__ == "__main__":
    main()
