"""
Bootstrap stability analysis for source bias clustering.

Loads pre-computed per-article framing features from data/article_framing.json
(produced by source_bias_clustering.py) and re-runs the fingerprinting +
clustering pipeline N times, each time resampling articles within each story
with replacement.

This gives:
  • co_cluster_matrix  — probability that each pair of sources lands in the
                         same cluster (0–1). More honest than a single hard
                         assignment; wide variance reveals model uncertainty.
  • source_distances_ci — 95% CI on each source's cosine distance from the
                          grand centroid across bootstrap iterations. Sources
                          with wide CIs should be shown as low-confidence.

The PRD specifically calls for this approach to distinguish the product from
existing bias databases that report point-estimate labels.

Outputs:
  data/bias_bootstrap.json
  visualizations/bias/co_cluster_heatmap.png

Run from repo root: python experiments/bootstrap_bias.py
"""

import json
import os
import sys
from collections import defaultdict
from itertools import combinations

import matplotlib.pyplot as plt
import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

FRAMING_PATH    = os.path.join(_DIR, "..", "data", "article_framing.json")
BOOTSTRAP_PATH  = os.path.join(_DIR, "..", "data", "bias_bootstrap.json")
OUT_DIR         = os.path.join(_DIR, "..", "visualizations", "bias")

N_BOOTSTRAP = 100
MIN_ARTICLES_PER_SOURCE = 3
DISTANCE_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Helpers shared with source_bias_clustering (duplicated to keep scripts
# self-contained and avoid circular imports)
# ---------------------------------------------------------------------------

def _build_feature_matrix(records: list[dict]) -> np.ndarray:
    """Normalized (N, D) feature matrix matching source_bias_clustering logic."""
    from sklearn.preprocessing import StandardScaler

    residuals = np.array([r["framing_residual"] for r in records], dtype=np.float32)
    bias      = np.array([[r["bias_signed"]]      for r in records], dtype=np.float32)
    charged   = np.array([[r["charged_density"]]  for r in records], dtype=np.float32)
    entity    = np.array(
        [[r["entity_ratios"].get(k, 0) for k in ("PERSON", "ORG", "GPE")] for r in records],
        dtype=np.float32,
    )

    def _scale(X):
        return StandardScaler().fit_transform(X) if X.shape[0] > 1 else X

    norm_residuals = _scale(residuals) / np.sqrt(residuals.shape[1])
    return np.hstack([norm_residuals, _scale(bias), _scale(charged), _scale(entity)])


def _recompute_residuals(records: list[dict]) -> list[dict]:
    """
    Recompute framing residuals for a bootstrap sample.

    After resampling within stories, the story centroid changes, so we must
    recompute residuals from the new centroid rather than using stored values.
    """
    story_embs: dict[int, list] = defaultdict(list)
    for r in records:
        emb = np.array(r["embedding"], dtype=np.float32)
        story_embs[r["story_id"]].append(emb)
    centroids = {sid: np.mean(embs, axis=0) for sid, embs in story_embs.items()}

    updated = []
    for r in records:
        emb = np.array(r["embedding"], dtype=np.float32)
        residual = emb - centroids[r["story_id"]]
        updated.append({**r, "framing_residual": residual.tolist()})
    return updated


def _run_single_clustering(records: list[dict]) -> dict[str, int] | None:
    """
    Fingerprint sources and cluster them for one bootstrap sample.
    Returns {source: cluster_id} or None if fewer than 2 sources qualify.
    """
    from sklearn.cluster import AgglomerativeClustering

    src_indices: dict[str, list] = defaultdict(list)
    for i, r in enumerate(records):
        src_indices[r["source"]].append(i)

    sources_ok, fingerprints_ok = [], []
    for src, idxs in src_indices.items():
        if len(idxs) >= MIN_ARTICLES_PER_SOURCE:
            feature_matrix = _build_feature_matrix([records[i] for i in idxs])
            sources_ok.append(src)
            fingerprints_ok.append(np.mean(feature_matrix, axis=0))

    if len(sources_ok) < 2:
        return None

    fingerprints = np.array(fingerprints_ok)
    labels = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=DISTANCE_THRESHOLD,
        metric="cosine",
        linkage="average",
    ).fit_predict(fingerprints)

    return {src: int(lbl) for src, lbl in zip(sources_ok, labels)}


def bootstrap_within_stories(
    records: list[dict], rng: np.random.Generator
) -> list[dict]:
    """
    Resample articles within each story with replacement, preserving story sizes.

    All records come from article_framing.json, which only contains articles
    from qualifying stories (story_id >= 0). Noise articles (story_id == -1)
    are excluded upstream in source_bias_clustering.py because no shared-story
    centroid exists to compute a meaningful residual from.
    """
    story_groups: dict[int, list] = defaultdict(list)
    for r in records:
        story_groups[r["story_id"]].append(r)

    resampled = []
    for group in story_groups.values():
        indices = rng.integers(0, len(group), size=len(group))
        resampled.extend(group[i] for i in indices)
    return resampled


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def plot_co_cluster_heatmap(
    sources: list[str],
    co_matrix: np.ndarray,
    out_dir: str,
) -> None:
    n = len(sources)
    fig, ax = plt.subplots(figsize=(max(6, n * 0.7), max(5, n * 0.6)))
    im = ax.imshow(co_matrix, vmin=0, vmax=1, cmap="YlOrRd")
    plt.colorbar(im, ax=ax, label="Co-cluster probability")
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(sources, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(sources, fontsize=8)
    ax.set_title(
        f"Source Co-Cluster Probability ({N_BOOTSTRAP} bootstrap iterations)\n"
        "1.0 = always same cluster  |  0.0 = never same cluster"
    )
    plt.tight_layout()
    out = os.path.join(out_dir, "co_cluster_heatmap.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        from sklearn.cluster import AgglomerativeClustering  # noqa: F401
        from sklearn.preprocessing import StandardScaler     # noqa: F401
    except ImportError as e:
        sys.exit(f"Missing dependency: {e}. Run: pip install scikit-learn")

    os.makedirs(OUT_DIR, exist_ok=True)

    if not os.path.exists(FRAMING_PATH):
        sys.exit(
            f"{FRAMING_PATH} not found.\n"
            "Run source_bias_clustering.py first to compute per-article features."
        )

    with open(FRAMING_PATH, "r", encoding="utf-8") as f:
        all_records = json.load(f)
    print(f"Loaded {len(all_records)} article framing records.")

    # Identify all sources that qualify in the full dataset
    src_counts: dict[str, int] = defaultdict(int)
    for r in all_records:
        src_counts[r["source"]] += 1
    all_sources = sorted(s for s, c in src_counts.items() if c >= MIN_ARTICLES_PER_SOURCE)

    if len(all_sources) < 2:
        sys.exit(
            f"Only {len(all_sources)} sources with ≥{MIN_ARTICLES_PER_SOURCE} articles. "
            "Need ≥2 to bootstrap. Collect more articles."
        )

    n_src = len(all_sources)
    src_idx = {src: i for i, src in enumerate(all_sources)}
    print(f"Sources to analyze: {all_sources}")

    co_cluster = np.zeros((n_src, n_src), dtype=np.float64)
    grand_distances: dict[str, list[float]] = defaultdict(list)

    rng = np.random.default_rng(seed=42)

    print(f"\nRunning {N_BOOTSTRAP} bootstrap iterations...")
    for iteration in range(N_BOOTSTRAP):
        if (iteration + 1) % 10 == 0:
            print(f"  Iteration {iteration + 1}/{N_BOOTSTRAP}")

        # Resample within stories, then recompute residuals from new centroids
        sample = bootstrap_within_stories(all_records, rng)
        sample = _recompute_residuals(sample)

        assignments = _run_single_clustering(sample)
        if assignments is None:
            continue

        # Update co-cluster counts
        present = [s for s in all_sources if s in assignments]
        for s1, s2 in combinations(present, 2):
            if assignments[s1] == assignments[s2]:
                i, j = src_idx[s1], src_idx[s2]
                co_cluster[i, j] += 1
                co_cluster[j, i] += 1

        # Source distances from grand centroid in this iteration
        present_fingerprints = []
        present_sources = []
        for src in present:
            src_records = [r for r in sample if r["source"] == src]
            if len(src_records) >= MIN_ARTICLES_PER_SOURCE:
                fm = _build_feature_matrix(src_records)
                fp = np.mean(fm, axis=0)
                present_sources.append(src)
                present_fingerprints.append(fp)

        if present_fingerprints:
            fps = np.array(present_fingerprints)
            grand_centroid = np.mean(fps, axis=0)
            for src, fp in zip(present_sources, present_fingerprints):
                norm_fp = np.linalg.norm(fp)
                norm_gc = np.linalg.norm(grand_centroid)
                if norm_fp > 0 and norm_gc > 0:
                    cos_sim = np.dot(fp, grand_centroid) / (norm_fp * norm_gc)
                    grand_distances[src].append(float(1.0 - cos_sim))

    # Normalize co-cluster matrix to probabilities
    # Diagonal = 1.0 (source always co-clusters with itself)
    co_cluster /= N_BOOTSTRAP
    np.fill_diagonal(co_cluster, 1.0)

    # 95% CI for each source's distance from grand centroid
    source_ci: dict[str, dict] = {}
    for src in all_sources:
        dists = grand_distances.get(src, [])
        if len(dists) >= 5:
            lo, hi = float(np.percentile(dists, 2.5)), float(np.percentile(dists, 97.5))
            mean = float(np.mean(dists))
        else:
            lo = hi = mean = None
        source_ci[src] = {
            "n_samples": len(dists),
            "mean_distance": round(mean, 4) if mean is not None else None,
            "ci_lo": round(lo, 4) if lo is not None else None,
            "ci_hi": round(hi, 4) if hi is not None else None,
            "low_confidence": (hi - lo > 0.3) if (lo is not None and hi is not None) else True,
        }

    # Save results
    output = {
        "n_bootstrap": N_BOOTSTRAP,
        "source_list": all_sources,
        "co_cluster_matrix": co_cluster.tolist(),
        "source_distances_ci": source_ci,
    }
    with open(BOOTSTRAP_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nSaved bootstrap results → {BOOTSTRAP_PATH}")

    # Print CI summary
    print("\nSource distance CIs (from grand centroid):")
    for src in all_sources:
        ci = source_ci[src]
        if ci["mean_distance"] is not None:
            flag = " ⚠ low-confidence" if ci["low_confidence"] else ""
            print(
                f"  {src}: mean={ci['mean_distance']:.3f} "
                f"[{ci['ci_lo']:.3f}, {ci['ci_hi']:.3f}]{flag}"
            )
        else:
            print(f"  {src}: insufficient samples")

    # Heatmap
    print("\nGenerating co-cluster heatmap...")
    plot_co_cluster_heatmap(all_sources, co_cluster, OUT_DIR)
    print("Done.")


if __name__ == "__main__":
    main()
