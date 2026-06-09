"""
Run politicalBiasBERT on every article with extracted text and plot
signed-bias distributions per source as stacked box-and-whisker plots.

Assumes story_clustering.py has already been run so that:
  data/scraped_text.json  — full-text cache
  data/articles.json      — article metadata

Reuses bias scores already computed in data/article_framing.json (if present)
so as not to re-run the model on articles already processed.

Saves:
  data/bias_all_articles.json            — {url: {source, bias_label, bias_score, bias_signed}}
  visualizations/bias/bias_by_source.png — box-and-whisker plot

Run from repo root: python experiments/bias_by_source.py
"""

import json
import os
import sys

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from tqdm import tqdm

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

ARTICLES_PATH     = os.path.join(_DIR, "..", "data", "articles.json")
SCRAPED_TEXT_PATH = os.path.join(_DIR, "..", "data", "scraped_text.json")
FRAMING_PATH      = os.path.join(_DIR, "..", "data", "article_framing.json")
OUTPUT_PATH       = os.path.join(_DIR, "..", "data", "bias_all_articles.json")
OUT_DIR           = os.path.join(_DIR, "..", "visualizations", "bias")

_BIAS_LABEL_MAP = {
    "LABEL_0": "Left", "LABEL_1": "Center", "LABEL_2": "Right",
    "0": "Left", "1": "Center", "2": "Right",
}

BIAS_COLORS = {"Left": "#4a90d9", "Center": "#888888", "Right": "#e05c4a"}

# --- Scoring configuration -------------------------------------------------
# Max tokens per inference window. politicalBiasBERT is a BERT model capped at
# 512 tokens, so long articles are split into windows of this size and the
# per-window probability vectors are length-weighted averaged (see _chunk_text
# / _aggregate_probs). This stops us from classifying only the (topic-heavy)
# lede of an article.
MAX_TOKENS = 512

# Center "dead zone". The signed score is P(Right) - P(Left); an article is
# labelled Center when the model is not confident (top class below
# CENTER_CONF_THRESHOLD) or when Left/Right are nearly tied (signed magnitude
# below CENTER_MARGIN). Without this, near-coin-flip predictions were being
# given hard Left/Right labels.
CENTER_CONF_THRESHOLD = 0.50
CENTER_MARGIN = 0.10


def _normalize_label(raw: str) -> str:
    return _BIAS_LABEL_MAP.get(raw, raw).capitalize()


def _signed_bias(label: str, score: float) -> float:
    """Legacy helper kept for backward compatibility with experiment scripts."""
    if label == "Right":
        return score
    if label == "Left":
        return -score
    return 0.0


def _chunk_text(text: str, tokenizer, max_tokens: int = MAX_TOKENS) -> list[tuple[str, int]]:
    """
    Split text into <=max_tokens-token windows for the model.

    Returns a list of (chunk_text, token_count) so chunks can be length-weighted
    when averaging. Leaves room for the [CLS]/[SEP] special tokens.
    """
    ids = tokenizer.encode(text, add_special_tokens=False, truncation=False)
    if not ids:
        return []
    window = max(1, max_tokens - 2)
    chunks: list[tuple[str, int]] = []
    for start in range(0, len(ids), window):
        piece = ids[start:start + window]
        if not piece:
            break
        chunks.append((tokenizer.decode(piece), len(piece)))
    return chunks


def _aggregate_probs(chunk_preds: list[list[dict]], weights: list[int]) -> dict[str, float]:
    """
    Length-weighted average of per-chunk class probabilities.

    chunk_preds: per chunk, the pipeline's all-scores output (list of
    {label, score}). Returns {"Left": p, "Center": p, "Right": p}.
    """
    agg = {"Left": 0.0, "Center": 0.0, "Right": 0.0}
    total = sum(weights) or 1
    for preds, w in zip(chunk_preds, weights):
        frac = w / total
        for d in preds:
            name = _normalize_label(d["label"])
            if name in agg:
                agg[name] += d["score"] * frac
    return agg


def _label_from_probs(probs: dict[str, float]) -> tuple[str, float]:
    """
    Turn a {Left, Center, Right} probability vector into (label, signed_score).

    signed = P(Right) - P(Left), in [-1, 1]. Applies the Center dead zone so
    low-confidence / near-tied articles are labelled Center rather than given a
    spurious hard Left/Right label.
    """
    signed = probs["Right"] - probs["Left"]
    top_label = max(probs, key=probs.get)
    if probs[top_label] < CENTER_CONF_THRESHOLD or abs(signed) < CENTER_MARGIN:
        return "Center", signed
    return top_label, signed


def load_cached_framing(path: str) -> dict[str, dict]:
    """Load already-computed bias results from article_framing.json keyed by URL."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        records = json.load(f)
    return {
        r["url"]: {
            "source": r["source"],
            "bias_label": r["bias_label"],
            "bias_score": r["bias_score"],
            "bias_signed": r["bias_signed"],
        }
        for r in records
        if "bias_label" in r
    }


def _has_new_scores(rec: dict) -> bool:
    """True if a cached entry was produced by the current (full-distribution) scorer."""
    return "prob_right" in rec


def run_bias_pipeline(articles, text_cache, cached) -> dict[str, dict]:
    """
    Return per-article bias scores for all articles with extractable text.

    Each entry is {source, bias_label, bias_score, bias_signed,
    prob_left, prob_center, prob_right}. The full article text is scored in
    <=512-token windows whose probability vectors are length-weighted averaged,
    and a Center dead zone is applied (see _label_from_probs).

    Reuses cached scores where available. Legacy cached entries that predate the
    full-distribution scorer (no prob_* fields) are re-scored so a single re-run
    upgrades them in place.
    """
    try:
        from transformers import pipeline
    except ImportError:
        sys.exit("Missing dependency: transformers. Run: pip install transformers torch")

    from collections import defaultdict

    # Determine which articles still need scoring (new ones + legacy upgrades)
    to_score = []
    for a in articles:
        url = a.get("url", "")
        if url in cached and _has_new_scores(cached[url]):
            continue
        entry = text_cache.get(url, {})
        text = entry.get("text") or a.get("description") or a.get("title", "")
        if text.strip():
            to_score.append((a, text))

    results: dict[str, dict] = dict(cached)

    if to_score:
        legacy = sum(1 for a, _ in to_score if a.get("url", "") in cached)
        print(
            f"Loading politicalBiasBERT for {len(to_score)} articles "
            f"({len(to_score) - legacy} new, {legacy} legacy upgrade)..."
        )
        bias_pipe = pipeline(
            "text-classification",
            model="bucketresearch/politicalBiasBERT",
            top_k=None,  # return all class probabilities, not just the top one
        )
        tokenizer = bias_pipe.tokenizer

        # Flatten every article into <=512-token chunks, score in one batch,
        # then regroup so each article averages its own chunks.
        all_chunks: list[str] = []
        chunk_owner: list[int] = []
        chunk_weight: list[int] = []
        for i, (_, text) in enumerate(to_score):
            chunks = _chunk_text(text, tokenizer) or [(text, 1)]
            for ctext, wt in chunks:
                all_chunks.append(ctext)
                chunk_owner.append(i)
                chunk_weight.append(wt)

        print(
            f"Running inference on {len(all_chunks)} chunks "
            f"from {len(to_score)} articles..."
        )
        batch_size = 8
        preds: list[list[dict]] = []
        with tqdm(total=len(all_chunks), desc="Scoring chunks", unit="chunk") as bar:
            for start in range(0, len(all_chunks), batch_size):
                batch = all_chunks[start:start + batch_size]
                preds.extend(
                    bias_pipe(batch, truncation=True, max_length=MAX_TOKENS)
                )
                bar.update(len(batch))

        grouped: dict[int, list[tuple[list[dict], int]]] = defaultdict(list)
        for owner, wt, pred in zip(chunk_owner, chunk_weight, preds):
            grouped[owner].append((pred, wt))

        for i, (a, _) in enumerate(to_score):
            chunk_list = grouped[i]
            probs = _aggregate_probs(
                [p for p, _ in chunk_list], [w for _, w in chunk_list]
            )
            label, signed = _label_from_probs(probs)
            url = a.get("url", "")
            results[url] = {
                "source": a.get("source", "unknown"),
                "bias_label": label,
                "bias_score": round(max(probs.values()), 4),
                "bias_signed": round(signed, 4),
                "prob_left": round(probs["Left"], 4),
                "prob_center": round(probs["Center"], 4),
                "prob_right": round(probs["Right"], 4),
            }
    else:
        print("All articles already have cached bias scores — skipping model inference.")

    # Fill in source for cached entries (in case framing cache lacked it)
    url_to_src = {a.get("url", ""): a.get("source", "unknown") for a in articles}
    for url, rec in results.items():
        if not rec.get("source"):
            rec["source"] = url_to_src.get(url, "unknown")

    return results


def plot_bias_by_source(results: dict[str, dict], out_dir: str) -> None:
    """
    Box-and-whisker plot: x = source, y = bias_signed score.
    Each article is also shown as a jittered point colored by label.
    Sources sorted by median bias_signed (left-leaning on the left).
    """
    from collections import defaultdict

    src_data: dict[str, list] = defaultdict(list)
    src_labels: dict[str, list] = defaultdict(list)
    for rec in results.values():
        src = rec["source"]
        src_data[src].append(rec["bias_signed"])
        src_labels[src].append(rec["bias_label"])

    # Only include sources with ≥2 articles so box plots are meaningful
    src_data = {s: v for s, v in src_data.items() if len(v) >= 2}
    if not src_data:
        print("Not enough data to plot (need ≥2 articles per source).")
        return

    # Sort sources by median signed bias
    sources = sorted(src_data, key=lambda s: float(np.median(src_data[s])))
    n = len(sources)

    fig_width = max(10, n * 0.9)
    fig, ax = plt.subplots(figsize=(fig_width, 7))

    box_data = [src_data[s] for s in sources]
    bp = ax.boxplot(
        box_data,
        positions=range(n),
        widths=0.5,
        patch_artist=True,
        medianprops=dict(color="black", linewidth=2),
        whiskerprops=dict(linewidth=1.2),
        capprops=dict(linewidth=1.2),
        flierprops=dict(marker="", linestyle="none"),  # hide default outlier markers
    )

    # Neutral grey fill for boxes
    for patch in bp["boxes"]:
        patch.set_facecolor("#e8e8e8")
        patch.set_alpha(0.7)

    # Jitter individual articles as colored dots
    rng = np.random.default_rng(seed=0)
    for xi, src in enumerate(sources):
        vals = src_data[src]
        labels = src_labels[src]
        jitter = rng.uniform(-0.18, 0.18, size=len(vals))
        for xj, (v, lbl) in enumerate(zip(vals, labels)):
            ax.scatter(
                xi + jitter[xj],
                v,
                color=BIAS_COLORS.get(lbl, "#aaaaaa"),
                s=28,
                alpha=0.75,
                zorder=3,
                linewidths=0,
            )

    # Reference lines
    ax.axhline(0, color="#333333", linewidth=0.8, linestyle="--", alpha=0.6)
    ax.axhline(0.5, color=BIAS_COLORS["Right"], linewidth=0.5, linestyle=":", alpha=0.4)
    ax.axhline(-0.5, color=BIAS_COLORS["Left"], linewidth=0.5, linestyle=":", alpha=0.4)

    ax.set_xticks(range(n))
    ax.set_xticklabels(sources, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Signed Bias Score  (← Left  |  Center  |  Right →)", fontsize=10)
    ax.set_xlabel("Source", fontsize=10)
    ax.set_title(
        "politicalBiasBERT — Article-Level Bias by Source\n"
        "(sources sorted by median; each dot = one article)",
        fontsize=12,
    )
    ax.set_ylim(-1.05, 1.05)
    ax.set_xlim(-0.7, n - 0.3)

    legend_patches = [
        mpatches.Patch(color=BIAS_COLORS["Left"],   label="Left"),
        mpatches.Patch(color=BIAS_COLORS["Center"], label="Center"),
        mpatches.Patch(color=BIAS_COLORS["Right"],  label="Right"),
    ]
    ax.legend(handles=legend_patches, loc="upper left", fontsize=9)

    plt.tight_layout()
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "bias_by_source.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def main() -> None:
    for path, label in [
        (ARTICLES_PATH, "articles.json"),
        (SCRAPED_TEXT_PATH, "scraped_text.json"),
    ]:
        if not os.path.exists(path):
            sys.exit(f"{label} not found at {path}. Run story_clustering.py first.")

    with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
        articles = json.load(f)
    with open(SCRAPED_TEXT_PATH, "r", encoding="utf-8") as f:
        text_cache = json.load(f)

    print(f"Articles: {len(articles)}  |  Text cache entries: {len(text_cache)}")

    cached = load_cached_framing(FRAMING_PATH)
    print(f"Reusing {len(cached)} cached bias scores from article_framing.json")

    results = run_bias_pipeline(articles, text_cache, cached)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved all bias scores -> {OUTPUT_PATH}  ({len(results)} articles)")

    # Summary
    from collections import Counter
    label_counts = Counter(r["bias_label"] for r in results.values())
    src_counts = Counter(r["source"] for r in results.values())
    print(f"\nLabel distribution: {dict(label_counts)}")
    print(f"Sources: {len(src_counts)}  (top 5: {dict(src_counts.most_common(5))})")

    print("\nGenerating plot...")
    plot_bias_by_source(results, OUT_DIR)
    print("Done.")


if __name__ == "__main__":
    main()
