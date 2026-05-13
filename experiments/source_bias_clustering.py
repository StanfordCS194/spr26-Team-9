"""
Source-level bias clustering via bootstrapped framing residuals.

For each article in stories with ≥3 distinct sources, this script builds a
framing feature vector that captures HOW a source covers a story rather than
WHAT it covers:

  • Framing residual  — body embedding minus story centroid (the "how" signal)
  • politicalBiasBERT — signed Left/Center/Right score
  • Charged-language density — CHARGED_LEXICON hits per 1000 tokens
  • Entity emphasis  — PERSON / ORG / GPE counts per 1000 words (spaCy NER)

Each feature group is independently normalized before concatenation so the
384-dim embedding doesn't numerically dominate the scalar features.  A source's
fingerprint is the mean framing vector across its articles (min 3).

Sources are then clustered with AgglomerativeClustering (cosine / average-linkage)
and visualized as a dendrogram — which shows *distance*, not just bucket membership,
so users see how close sources are. Cluster interpretation relies on observable
framing differences (entity emphasis, charged language) rather than political labels.

Outputs:
  data/article_framing.json        — per-article feature records (used by bootstrap)
  data/source_bias.json            — per-source fingerprints, cluster IDs, stats
  visualizations/bias/dendrogram.png
  visualizations/bias/cluster_features.png

Run from repo root: python experiments/source_bias_clustering.py
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

ARTICLES_PATH     = os.path.join(_DIR, "..", "data", "articles.json")
STORIES_PATH      = os.path.join(_DIR, "..", "data", "stories.json")
SCRAPED_TEXT_PATH = os.path.join(_DIR, "..", "data", "scraped_text.json")
EMBEDDINGS_PATH   = os.path.join(_DIR, "..", "data", "article_embeddings.json")
FRAMING_PATH      = os.path.join(_DIR, "..", "data", "article_framing.json")
SOURCE_BIAS_PATH  = os.path.join(_DIR, "..", "data", "source_bias.json")
OUT_DIR           = os.path.join(_DIR, "..", "visualizations", "bias")

MIN_SOURCES_PER_STORY = 3   # stories with fewer distinct sources are excluded
MIN_ARTICLES_PER_SOURCE = 3  # sources with fewer articles get a low-confidence flag

_BIAS_LABEL_MAP = {
    "LABEL_0": "Left", "LABEL_1": "Center", "LABEL_2": "Right",
    "0": "Left", "1": "Center", "2": "Right",
}

CHARGED_LEXICON = [
    "slammed", "blasted", "radical", "shocking", "outrageous", "destroyed",
    "attacked", "failed", "crisis", "disaster", "corrupt", "lies", "hoax",
    "extreme", "dangerous", "invasion", "threat", "devastating", "chaos", "alarming",
]


# ---------------------------------------------------------------------------
# Feature helpers
# ---------------------------------------------------------------------------

def _normalize_bias_label(raw: str) -> str:
    return _BIAS_LABEL_MAP.get(raw, raw).capitalize()


def _signed_bias(label: str, score: float) -> float:
    if label == "Right":
        return score
    if label == "Left":
        return -score
    return 0.0


def _charged_counts(text: str) -> dict[str, int]:
    return {
        w: len(re.findall(r"\b" + re.escape(w) + r"\b", text, re.IGNORECASE))
        for w in CHARGED_LEXICON
    }


def _charged_density(text: str) -> float:
    """Total charged-word occurrences per 1000 tokens."""
    words = text.split()
    if not words:
        return 0.0
    total = sum(_charged_counts(text).values())
    return total / len(words) * 1000


def _entity_ratios(text: str, nlp) -> dict[str, float]:
    """PERSON / ORG / GPE entity counts per 1000 words via spaCy NER."""
    words = text.split()
    n_words = max(len(words), 1)
    doc = nlp(text[:50_000])
    counts = Counter(
        ent.label_ for ent in doc.ents if ent.label_ in ("PERSON", "ORG", "GPE")
    )
    return {
        label: round(counts.get(label, 0) / n_words * 1000, 4)
        for label in ("PERSON", "ORG", "GPE")
    }


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def compute_article_framing(
    articles: list[dict],
    stories: dict[str, int],
    text_cache: dict[str, dict],
    model,
    bias_pipe,
    nlp,
) -> list[dict]:
    """
    Compute per-article framing feature records for qualifying stories.

    A qualifying story has ≥ MIN_SOURCES_PER_STORY distinct sources, which
    ensures the story centroid is a meaningful cross-source consensus rather
    than a single outlet's framing.

    Articles with story_id == -1 (HDBSCAN noise) are excluded: without a
    real shared-story centroid there is no meaningful residual to compute.
    """
    # Identify qualifying stories
    src_by_story: dict[int, set] = defaultdict(set)
    url_to_src = {a.get("url", ""): a.get("source", "") for a in articles}
    for url, sid in stories.items():
        if sid >= 0:
            src_by_story[sid].add(url_to_src.get(url, ""))
    qualifying = {sid for sid, srcs in src_by_story.items() if len(srcs) >= MIN_SOURCES_PER_STORY}

    if not qualifying:
        print(
            f"No stories with ≥{MIN_SOURCES_PER_STORY} distinct sources. "
            "Try lowering MIN_SOURCES_PER_STORY or running more diverse article sources."
        )
        return []

    # Filter articles
    qualifying_urls = {url for url, sid in stories.items() if sid in qualifying}
    filtered = [a for a in articles if a.get("url", "") in qualifying_urls]
    print(
        f"Qualifying stories: {len(qualifying)} (≥{MIN_SOURCES_PER_STORY} sources)  "
        f"| Articles: {len(filtered)}"
    )

    # Resolve body text for each article
    texts = []
    for a in filtered:
        entry = text_cache.get(a.get("url", ""), {})
        texts.append(entry.get("text") or a.get("description") or a.get("title", ""))

    # Load embeddings from story_clustering cache; re-encode only missing articles.
    # This ensures both scripts use embeddings from the same model call on the
    # same text inputs, so story centroids and residuals are in the same space.
    emb_cache: dict[str, list] = {}
    if os.path.exists(EMBEDDINGS_PATH):
        with open(EMBEDDINGS_PATH, "r", encoding="utf-8") as f:
            emb_cache = json.load(f)

    missing_idx = [i for i, a in enumerate(filtered) if a.get("url", "") not in emb_cache]
    if missing_idx:
        print(f"Encoding {len(missing_idx)} articles not in embedding cache...")
        missing_texts = [texts[i] for i in missing_idx]
        new_embs = model.encode(missing_texts, show_progress_bar=True, batch_size=16)
        for i, emb in zip(missing_idx, new_embs):
            emb_cache[filtered[i].get("url", "")] = emb.tolist()
        with open(EMBEDDINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(emb_cache, f, ensure_ascii=False)
    else:
        print(f"Using cached embeddings from {EMBEDDINGS_PATH} (no re-encoding needed).")

    embeddings = np.array(
        [emb_cache[a.get("url", "")] for a in filtered], dtype=np.float32
    )

    # Story centroids (mean embedding of all articles in each story)
    story_embs: dict[int, list] = defaultdict(list)
    for a, emb in zip(filtered, embeddings):
        sid = stories.get(a.get("url", ""), -1)
        story_embs[sid].append(emb)
    story_centroids = {sid: np.mean(embs, axis=0) for sid, embs in story_embs.items()}

    # politicalBiasBERT
    print(f"Running politicalBiasBERT on {len(filtered)} articles...")
    bias_results = bias_pipe(texts, batch_size=4, truncation=True, max_length=512)

    # spaCy NER entity ratios
    print("Computing NER entity ratios...")
    entity_ratio_list = [_entity_ratios(t, nlp) for t in texts]

    records = []
    for a, emb, text, bias, ent_ratios in zip(
        filtered, embeddings, texts, bias_results, entity_ratio_list
    ):
        url = a.get("url", "")
        sid = stories.get(url, -1)
        residual = emb - story_centroids[sid]
        bias_label = _normalize_bias_label(bias["label"])
        c_counts = _charged_counts(text)
        records.append({
            "url": url,
            "source": a.get("source", ""),
            "story_id": sid,
            # Raw body embedding — needed for bootstrap to recompute residuals after resampling
            "embedding": emb.tolist(),
            # Framing residual from full-dataset centroid
            "framing_residual": residual.tolist(),
            "bias_label": bias_label,
            "bias_score": round(float(bias["score"]), 4),
            "bias_signed": round(_signed_bias(bias_label, float(bias["score"])), 4),
            "charged_density": round(_charged_density(text), 4),
            "charged_counts": c_counts,
            "entity_ratios": ent_ratios,
        })

    return records


def build_normalized_feature_matrix(records: list[dict]) -> np.ndarray:
    """
    Build a normalized (N, D) feature matrix.

    Each feature group is independently scaled to zero-mean / unit-variance across
    all N articles. The embedding residual block is then divided by sqrt(n_dims) so
    its total L2 magnitude matches the scalar feature block and doesn't dominate
    cosine similarity during source clustering.
    """
    from sklearn.preprocessing import StandardScaler

    residuals = np.array([r["framing_residual"] for r in records], dtype=np.float32)
    bias      = np.array([[r["bias_signed"]]      for r in records], dtype=np.float32)
    charged   = np.array([[r["charged_density"]]  for r in records], dtype=np.float32)
    entity    = np.array(
        [[r["entity_ratios"].get(k, 0) for k in ("PERSON", "ORG", "GPE")] for r in records],
        dtype=np.float32,
    )

    def _scale(X: np.ndarray) -> np.ndarray:
        if X.shape[0] <= 1:
            return X
        return StandardScaler().fit_transform(X)

    norm_residuals = _scale(residuals) / np.sqrt(residuals.shape[1])
    norm_bias      = _scale(bias)
    norm_charged   = _scale(charged)
    norm_entity    = _scale(entity)

    return np.hstack([norm_residuals, norm_bias, norm_charged, norm_entity])


def fingerprint_sources(
    records: list[dict],
    feature_matrix: np.ndarray,
) -> tuple[list[str], np.ndarray, dict]:
    """
    Average normalized feature rows per source to get fingerprints.

    Returns (sources, fingerprints, source_stats).
    Sources with < MIN_ARTICLES_PER_SOURCE are included in stats but flagged
    as low-confidence and excluded from clustering.
    """
    src_indices: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        src_indices[r["source"]].append(i)

    sources_ok, fingerprints_ok = [], []
    source_stats = {}

    for src in sorted(src_indices):
        idxs = src_indices[src]
        arts = [records[i] for i in idxs]
        n = len(arts)
        flagged = n < MIN_ARTICLES_PER_SOURCE

        if flagged:
            print(f"  Low-confidence: {src!r} ({n} articles < {MIN_ARTICLES_PER_SOURCE})")
        else:
            fp = np.mean(feature_matrix[idxs], axis=0)
            sources_ok.append(src)
            fingerprints_ok.append(fp)

        # Aggregate interpretable stats
        top_charged = Counter()
        for a in arts:
            top_charged.update(a.get("charged_counts", {}))
        top_charged_words = [
            {"word": w, "count": c}
            for w, c in top_charged.most_common(5)
            if c > 0
        ]

        mean_entity = {
            k: round(float(np.mean([a["entity_ratios"].get(k, 0) for a in arts])), 4)
            for k in ("PERSON", "ORG", "GPE")
        }

        source_stats[src] = {
            "n_articles": n,
            "flagged_low_confidence": flagged,
            "cluster_id": None,
            "mean_bias_signed": round(float(np.mean([a["bias_signed"] for a in arts])), 4),
            "mean_charged_density": round(float(np.mean([a["charged_density"] for a in arts])), 4),
            "top_charged_words": top_charged_words,
            "mean_entity_ratios": mean_entity,
            "fingerprint": None,
        }

    fingerprints = np.array(fingerprints_ok) if fingerprints_ok else np.array([])
    # Store fingerprints in stats for JSON export
    for src, fp in zip(sources_ok, fingerprints_ok):
        source_stats[src]["fingerprint"] = fp.tolist()

    return sources_ok, fingerprints, source_stats


def cluster_sources(
    sources: list[str],
    fingerprints: np.ndarray,
    source_stats: dict,
    distance_threshold: float = 0.5,
) -> tuple[np.ndarray, object]:
    """
    Run AgglomerativeClustering with cosine/average-linkage.
    Returns (cluster_labels, scipy_linkage_matrix).
    """
    from sklearn.cluster import AgglomerativeClustering
    from scipy.spatial.distance import pdist, squareform
    from scipy.cluster.hierarchy import linkage

    if len(sources) < 2:
        print("Not enough sources to cluster.")
        for src in sources:
            source_stats[src]["cluster_id"] = 0
        return np.zeros(len(sources), dtype=int), None

    clusterer = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="cosine",
        linkage="average",
    )
    labels = clusterer.fit_predict(fingerprints)
    for src, label in zip(sources, labels):
        source_stats[src]["cluster_id"] = int(label)

    # Scipy linkage for dendrogram (uses condensed distance matrix)
    dist_condensed = pdist(fingerprints, metric="cosine")
    Z = linkage(dist_condensed, method="average")

    return labels, Z


# ---------------------------------------------------------------------------
# Visualizations
# ---------------------------------------------------------------------------

def plot_dendrogram(sources: list[str], Z, out_dir: str) -> None:
    from scipy.cluster.hierarchy import dendrogram

    fig, ax = plt.subplots(figsize=(max(10, len(sources) * 0.8), 6))
    dendrogram(
        Z,
        labels=sources,
        ax=ax,
        leaf_rotation=45,
        leaf_font_size=9,
    )
    ax.set_title("Source Framing Similarity Dendrogram\n(cosine distance on framing fingerprints)")
    ax.set_ylabel("Cosine Distance")
    ax.set_xlabel("Source")
    plt.tight_layout()
    out = os.path.join(out_dir, "dendrogram.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_cluster_features(source_stats: dict, out_dir: str) -> None:
    """
    For each cluster, show mean signed-bias, charged-language density, and
    entity emphasis ratios as grouped bar charts — observable differences only,
    no political labels.
    """
    clustered = {
        src: s for src, s in source_stats.items()
        if not s["flagged_low_confidence"] and s["cluster_id"] is not None
    }
    if not clustered:
        return

    cluster_ids = sorted(set(s["cluster_id"] for s in clustered.values()))
    n_clusters = len(cluster_ids)
    features = ["mean_bias_signed", "mean_charged_density"]
    entity_keys = ["PERSON", "ORG", "GPE"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: bias + charged density per cluster
    ax = axes[0]
    x = np.arange(n_clusters)
    width = 0.35
    for fi, feat in enumerate(features):
        vals = []
        for cid in cluster_ids:
            srcs_in_cluster = [s for src, s in clustered.items() if s["cluster_id"] == cid]
            vals.append(np.mean([s[feat] for s in srcs_in_cluster]))
        ax.bar(x + fi * width, vals, width, label=feat.replace("mean_", ""))
    ax.set_xticks(x + width / 2)
    ax.set_xticklabels([f"Cluster {cid}" for cid in cluster_ids])
    ax.set_title("Cluster-Level Framing Features")
    ax.axhline(0, color="black", linewidth=0.6)
    ax.legend()

    # Right: entity emphasis per cluster
    ax = axes[1]
    width = 0.25
    for ei, key in enumerate(entity_keys):
        vals = []
        for cid in cluster_ids:
            srcs_in_cluster = [s for src, s in clustered.items() if s["cluster_id"] == cid]
            vals.append(np.mean([s["mean_entity_ratios"].get(key, 0) for s in srcs_in_cluster]))
        ax.bar(x + ei * width, vals, width, label=key)
    ax.set_xticks(x + width)
    ax.set_xticklabels([f"Cluster {cid}" for cid in cluster_ids])
    ax.set_title("Entity Emphasis per Cluster (mentions / 1000 words)")
    ax.legend()

    plt.tight_layout()
    out = os.path.join(out_dir, "cluster_features.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        from sentence_transformers import SentenceTransformer
        from transformers import pipeline
        import spacy
    except ImportError as e:
        sys.exit(f"Missing dependency: {e}")

    os.makedirs(OUT_DIR, exist_ok=True)

    # Load data
    with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(STORIES_PATH, "r", encoding="utf-8") as f:
        stories = json.load(f)
    with open(SCRAPED_TEXT_PATH, "r", encoding="utf-8") as f:
        text_cache = json.load(f)
    print(f"Articles: {len(articles)}  |  Stories assigned: {len(stories)}")

    # --- Load models ---
    print("\nLoading sentence-transformer (all-MiniLM-L6-v2)...")
    embed_model = SentenceTransformer("all-MiniLM-L6-v2")

    print("Loading politicalBiasBERT...")
    bias_pipe = pipeline(
        "text-classification",
        model="bucketresearch/politicalBiasBERT",
        truncation=True,
        max_length=512,
    )

    print("Loading spaCy (en_core_web_sm)...")
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        sys.exit(
            "spaCy model not found. Run: python -m spacy download en_core_web_sm"
        )

    # --- Compute or load per-article framing features ---
    if os.path.exists(FRAMING_PATH):
        print(f"\nLoading cached article framing from {FRAMING_PATH}...")
        with open(FRAMING_PATH, "r", encoding="utf-8") as f:
            records = json.load(f)
    else:
        print("\nComputing per-article framing features...")
        records = compute_article_framing(
            articles, stories, text_cache, embed_model, bias_pipe, nlp
        )
        if not records:
            return
        with open(FRAMING_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print(f"Saved article framing → {FRAMING_PATH}")

    if not records:
        print("No records to cluster.")
        return

    print(f"\nBuilding normalized feature matrix for {len(records)} articles...")
    feature_matrix = build_normalized_feature_matrix(records)

    print("Fingerprinting sources...")
    sources, fingerprints, source_stats = fingerprint_sources(records, feature_matrix)
    print(f"Sources with ≥{MIN_ARTICLES_PER_SOURCE} articles: {len(sources)}")

    if len(sources) < 2:
        print("Need ≥2 sources for clustering. Collect more articles from diverse outlets.")
        return

    print("Clustering sources (cosine / average-linkage)...")
    _labels, Z = cluster_sources(sources, fingerprints, source_stats)

    # Sanity-check print
    cluster_to_srcs: dict[int, list] = defaultdict(list)
    for src in sources:
        cid = source_stats[src]["cluster_id"]
        cluster_to_srcs[cid].append(src)
    print("\nCluster assignments:")
    for cid, srcs in sorted(cluster_to_srcs.items()):
        print(f"  Cluster {cid}: {', '.join(srcs)}")

    # Save outputs
    with open(SOURCE_BIAS_PATH, "w", encoding="utf-8") as f:
        json.dump(source_stats, f, indent=2, ensure_ascii=False)
    print(f"\nSaved source bias → {SOURCE_BIAS_PATH}")

    # Visualizations
    print("\nGenerating visualizations...")
    if Z is not None:
        plot_dendrogram(sources, Z, OUT_DIR)
    plot_cluster_features(source_stats, OUT_DIR)
    print("Done.")


if __name__ == "__main__":
    main()
