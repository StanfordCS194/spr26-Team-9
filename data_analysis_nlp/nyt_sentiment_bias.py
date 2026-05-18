"""
Sentiment and political-bias analysis of NYT article titles using lightweight
HuggingFace models.

Models used:
  - sentiment:  distilbert-base-uncased-finetuned-sst-2-english (~260 MB)
  - bias:       typeform/distilbert-base-uncased-mnli via zero-shot (~250 MB)

Run from repo root: python experiments/sentiment_bias.py
"""

import json
import os
import textwrap

import matplotlib.pyplot as plt
from transformers import pipeline

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "nyt_articles.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "visualizations", "nyt")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sentiment_bias.json")

BIAS_LABELS = ["left-leaning", "centrist", "right-leaning"]
BIAS_COLORS = {"left-leaning": "#4f9eea", "centrist": "#2ca02c", "right-leaning": "#d62728"}
SENTIMENT_COLORS = {"POSITIVE": "#38b86b", "NEGATIVE": "#d62728"}


def load_articles(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_analysis(articles: list[dict]) -> list[dict]:
    """Run sentiment and zero-shot bias classification on each article title."""
    print("Loading sentiment model (distilbert-sst2)...")
    sentiment_pipe = pipeline(
        "sentiment-analysis",
        model="distilbert-base-uncased-finetuned-sst-2-english",
        truncation=True,
        max_length=128,
    )

    print("Loading zero-shot bias model (typeform/distilbert-mnli)...")
    bias_pipe = pipeline(
        "zero-shot-classification",
        model="typeform/distilbert-base-uncased-mnli",
    )

    titles = [a["title"] for a in articles]
    print(f"Analyzing {len(titles)} titles...")

    sentiment_results = sentiment_pipe(titles, batch_size=8)
    bias_results = bias_pipe(titles, candidate_labels=BIAS_LABELS, batch_size=8)

    results = []
    for article, sent, bias in zip(articles, sentiment_results, bias_results):
        results.append({
            "title": article["title"],
            "date": article["date"],
            "author": article.get("author", ""),
            "sentiment_label": sent["label"],
            "sentiment_score": round(sent["score"], 4),
            "bias_label": bias["labels"][0],
            "bias_score": round(bias["scores"][0], 4),
            "bias_scores": {
                label: round(score, 4)
                for label, score in zip(bias["labels"], bias["scores"])
            },
        })

    return results


def plot_sentiment_distribution(results: list[dict]) -> None:
    """Bar chart of positive vs negative title counts."""
    from collections import Counter
    counts = Counter(r["sentiment_label"] for r in results)
    labels = list(counts.keys())
    values = list(counts.values())
    colors = [SENTIMENT_COLORS.get(l, "#aaaaaa") for l in labels]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(labels, values, color=colors, width=0.5)
    ax.set_ylabel("Number of Articles")
    ax.set_title("NYT Title Sentiment Distribution")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "sentiment_distribution.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_bias_distribution(results: list[dict]) -> None:
    """Bar chart of left / centrist / right-leaning title counts."""
    from collections import Counter
    counts = Counter(r["bias_label"] for r in results)
    labels = BIAS_LABELS
    values = [counts.get(l, 0) for l in labels]
    colors = [BIAS_COLORS[l] for l in labels]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(labels, values, color=colors, width=0.5)
    ax.set_ylabel("Number of Articles")
    ax.set_title("NYT Title Political-Bias Distribution (zero-shot)")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "bias_distribution.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_per_article_sentiment(results: list[dict]) -> None:
    """Horizontal bar of sentiment confidence per article, sorted by score."""
    sorted_results = sorted(results, key=lambda r: r["sentiment_score"])
    labels = [
        textwrap.shorten(r["title"], width=55, placeholder="…")
        for r in sorted_results
    ]
    values = [
        r["sentiment_score"] if r["sentiment_label"] == "POSITIVE" else -r["sentiment_score"]
        for r in sorted_results
    ]
    colors = [SENTIMENT_COLORS[r["sentiment_label"]] for r in sorted_results]

    fig, ax = plt.subplots(figsize=(12, max(4, len(labels) * 0.38)))
    ax.barh(labels, values, color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("← Negative score     Positive score →")
    ax.set_title("NYT Title Sentiment Score per Article")
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "sentiment_per_article.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_per_article_bias(results: list[dict]) -> None:
    """Stacked horizontal bar showing left/centrist/right scores per article."""
    sorted_results = sorted(results, key=lambda r: r["bias_scores"].get("left-leaning", 0))
    labels = [
        textwrap.shorten(r["title"], width=55, placeholder="…")
        for r in sorted_results
    ]

    fig, ax = plt.subplots(figsize=(12, max(4, len(labels) * 0.38)))
    lefts = [0.0] * len(sorted_results)
    for bias_label in BIAS_LABELS:
        values = [r["bias_scores"].get(bias_label, 0) for r in sorted_results]
        ax.barh(labels, values, left=lefts, label=bias_label, color=BIAS_COLORS[bias_label])
        lefts = [l + v for l, v in zip(lefts, values)]

    ax.set_xlabel("Probability")
    ax.set_title("NYT Title Political-Bias Scores per Article (zero-shot)")
    ax.legend(loc="lower right")
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "bias_per_article.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    articles = load_articles(DATA_PATH)
    print(f"Loaded {len(articles)} articles.")

    results = run_analysis(articles)

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved results: {RESULTS_PATH}")

    plot_sentiment_distribution(results)
    plot_bias_distribution(results)
    plot_per_article_sentiment(results)
    plot_per_article_bias(results)
    print("Done.")
