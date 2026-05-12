"""
Sentiment and political-bias analysis of Fox News articles using full scraped text.

Data sources: data/current_articles.json and data/newsapi_articles.json
Text extraction: trafilatura (falls back to description, then title)

Models used:
  - roberta:  cardiffnlp/twitter-roberta-base-sentiment-latest
  - vader:    vaderSentiment (rule-based, compound score -1 to 1)
  - bias:     bucketresearch/politicalBiasBERT

Run from repo root: python experiments/fox_sentiment_bias.py
"""

import json
import os
import textwrap
from collections import Counter

import matplotlib.pyplot as plt
import trafilatura
from transformers import pipeline
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    
CURRENTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "current_articles.json")
NEWSAPI_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "newsapi_articles.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "visualizations", "fox")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fox_sentiment_bias.json")
SCRAPED_TEXT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fox_scraped_text.json")

_FOX_IDENTIFIERS = {"foxnews.com", "fox news", "fox business", "foxbusiness.com"}

ROBERTA_COLORS = {"positive": "#38b86b", "neutral": "#f0a500", "negative": "#d62728"}
BIAS_COLORS = {"Left": "#4f9eea", "Center": "#2ca02c", "Right": "#d62728"}

# politicalBiasBERT outputs numeric labels; map them to human-readable names.
_BIAS_LABEL_MAP = {
    "LABEL_0": "Left",
    "LABEL_1": "Center",
    "LABEL_2": "Right",
    "0": "Left",
    "1": "Center",
    "2": "Right",
}


def _normalize_bias_label(raw: str) -> str:
    label = _BIAS_LABEL_MAP.get(raw, raw)
    return label.capitalize()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _is_fox(article: dict) -> bool:
    """Return True if the article's source is Fox News."""
    source = (article.get("source") or "").lower()
    return any(ident in source for ident in _FOX_IDENTIFIERS)


def load_articles() -> list[dict]:
    """Load and merge CurrentsAPI and NewsAPI data, filtering to Fox News articles."""
    articles = []
    for path in (CURRENTS_PATH, NEWSAPI_PATH):
        with open(path, "r", encoding="utf-8") as f:
            articles.extend(json.load(f))
    return [a for a in articles if _is_fox(a)]


# ---------------------------------------------------------------------------
# Text scraping
# ---------------------------------------------------------------------------

def get_article_text(url: str) -> str | None:
    """Fetch and extract main article body using trafilatura."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            return trafilatura.extract(downloaded, include_comments=False)
    except Exception:
        pass
    return None


def resolve_text(article: dict, index: int, total: int) -> tuple[str, str]:
    """
    Return (text, source_label) for an article.
    Tries: scraped body → description → title.
    """
    url = article.get("url", "")
    print(f"  Scraping {index}/{total}: {url[:80]}")
    text = get_article_text(url)
    if text:
        return text, "scraped"
    desc = article.get("description") or ""
    if desc.strip():
        return desc, "description"
    return article.get("title", ""), "title"


# ---------------------------------------------------------------------------
# NLP analysis
# ---------------------------------------------------------------------------

def _vader_label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def run_analysis(articles: list[dict]) -> list[dict]:
    """Scrape article text and run all three NLP models."""
    total = len(articles)

    if os.path.exists(SCRAPED_TEXT_PATH):
        print(f"\nLoading cached scraped text from {SCRAPED_TEXT_PATH}...")
        with open(SCRAPED_TEXT_PATH, "r", encoding="utf-8") as f:
            scraped_records = json.load(f)
        url_to_record = {r["url"]: r for r in scraped_records}
        texts: list[tuple[str, str]] = [
            (url_to_record[a.get("url", "")]["text"], url_to_record[a.get("url", "")]["text_source"])
            if a.get("url", "") in url_to_record
            else (a.get("description") or a.get("title", ""), "description")
            for a in articles
        ]
    else:
        print("\nScraping article text...")
        texts: list[tuple[str, str]] = [
            resolve_text(a, i + 1, total) for i, a in enumerate(articles)
        ]
        scraped_records = [
            {"title": a["title"], "url": a.get("url", ""), "text_source": src, "text": body}
            for a, (body, src) in zip(articles, texts)
        ]
        with open(SCRAPED_TEXT_PATH, "w", encoding="utf-8") as f:
            json.dump(scraped_records, f, indent=2, ensure_ascii=False)
        print(f"Saved scraped text: {SCRAPED_TEXT_PATH}")

    print("\nLoading RoBERTa sentiment model...")
    roberta_pipe = pipeline(
        "text-classification",
        model="cardiffnlp/twitter-roberta-base-sentiment-latest",
        truncation=True,
        max_length=512,
    )

    print("Loading politicalBiasBERT model...")
    bias_pipe = pipeline(
        "text-classification",
        model="bucketresearch/politicalBiasBERT",
        truncation=True,
        max_length=512,
    )

    print("Loading VADER analyzer...")
    vader = SentimentIntensityAnalyzer()

    body_texts = [t for t, _ in texts]

    print(f"\nRunning RoBERTa on {total} articles...")
    roberta_results = roberta_pipe(body_texts, batch_size=4)

    print(f"Running politicalBiasBERT on {total} articles...")
    bias_results = bias_pipe(body_texts, batch_size=4)

    results = []
    for article, (body, src), roberta, bias in zip(articles, texts, roberta_results, bias_results):
        vader_scores = vader.polarity_scores(body)
        compound = round(vader_scores["compound"], 4)
        results.append({
            "title": article["title"],
            "url": article.get("url", ""),
            "date": article.get("date", ""),
            "author": article.get("author", ""),
            "source": article.get("source", ""),
            "text_source": src,
            "roberta_label": roberta["label"].lower(),
            "roberta_score": round(roberta["score"], 4),
            "vader_compound": compound,
            "vader_label": _vader_label(compound),
            "vader_scores": {
                "neg": round(vader_scores["neg"], 4),
                "neu": round(vader_scores["neu"], 4),
                "pos": round(vader_scores["pos"], 4),
            },
            "bias_label": _normalize_bias_label(bias["label"]),
            "bias_score": round(bias["score"], 4),
        })

    return results


# ---------------------------------------------------------------------------
# Visualizations
# ---------------------------------------------------------------------------

def plot_roberta_sentiment_distribution(results: list[dict]) -> None:
    """Bar chart of RoBERTa negative/neutral/positive article counts."""
    order = ["negative", "neutral", "positive"]
    counts = Counter(r["roberta_label"] for r in results)
    values = [counts.get(l, 0) for l in order]
    colors = [ROBERTA_COLORS[l] for l in order]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(order, values, color=colors, width=0.5)
    ax.set_ylabel("Number of Articles")
    ax.set_title("Fox News Sentiment Distribution (RoBERTa)")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_roberta_sentiment_distribution.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_vader_sentiment_distribution(results: list[dict]) -> None:
    """Bar chart of VADER negative/neutral/positive article counts."""
    order = ["negative", "neutral", "positive"]
    counts = Counter(r["vader_label"] for r in results)
    values = [counts.get(l, 0) for l in order]
    colors = [ROBERTA_COLORS[l] for l in order]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(order, values, color=colors, width=0.5)
    ax.set_ylabel("Number of Articles")
    ax.set_title("Fox News Sentiment Distribution (VADER)")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_vader_sentiment_distribution.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_vader_compound_histogram(results: list[dict]) -> None:
    """Histogram of VADER compound scores across all articles."""
    compounds = [r["vader_compound"] for r in results]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(compounds, bins=20, range=(-1, 1), color="#f0a500", edgecolor="white")
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("VADER Compound Score (← Negative   Positive →)")
    ax.set_ylabel("Number of Articles")
    ax.set_title("Fox News VADER Compound Score Distribution")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_vader_compound_histogram.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_bias_distribution(results: list[dict]) -> None:
    """Bar chart of Left/Center/Right article counts (politicalBiasBERT)."""
    order = ["Left", "Center", "Right"]
    counts = Counter(r["bias_label"] for r in results)
    values = [counts.get(l, 0) for l in order]
    colors = [BIAS_COLORS[l] for l in order]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(order, values, color=colors, width=0.5)
    ax.set_ylabel("Number of Articles")
    ax.set_title("Fox News Political Bias Distribution (politicalBiasBERT)")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_bias_distribution.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_sentiment_per_article(results: list[dict]) -> None:
    """Horizontal bar of RoBERTa sentiment score per article (positive right, negative left)."""
    sorted_results = sorted(results, key=lambda r: r["roberta_score"]
                            if r["roberta_label"] == "positive" else -r["roberta_score"])
    labels = [
        textwrap.shorten(r["title"], width=55, placeholder="…")
        for r in sorted_results
    ]
    values = [
        r["roberta_score"] if r["roberta_label"] == "positive" else -r["roberta_score"]
        for r in sorted_results
    ]
    colors = [ROBERTA_COLORS.get(r["roberta_label"], "#aaaaaa") for r in sorted_results]

    fig, ax = plt.subplots(figsize=(12, max(4, len(labels) * 0.38)))
    ax.barh(labels, values, color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("← Negative score     Positive score →")
    ax.set_title("Fox News Sentiment Score per Article (RoBERTa)")
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_sentiment_per_article.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_bias_per_article(results: list[dict]) -> None:
    """Horizontal bar of bias label and score per article (politicalBiasBERT)."""
    sorted_results = sorted(results, key=lambda r: r["bias_label"])
    labels = [
        textwrap.shorten(r["title"], width=55, placeholder="…")
        for r in sorted_results
    ]
    values = [r["bias_score"] for r in sorted_results]
    colors = [BIAS_COLORS.get(r["bias_label"], "#aaaaaa") for r in sorted_results]

    fig, ax = plt.subplots(figsize=(12, max(4, len(labels) * 0.38)))
    ax.barh(labels, values, color=colors)
    ax.set_xlabel("Confidence Score")
    ax.set_title("Fox News Political Bias Score per Article (politicalBiasBERT)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=BIAS_COLORS[l]) for l in ["Left", "Center", "Right"]]
    ax.legend(handles, ["Left", "Center", "Right"], loc="lower right")
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_bias_per_article.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fox News sentiment & bias analysis")
    parser.add_argument(
        "--max-articles", type=int, default=None, metavar="N",
        help="Limit processing to the first N articles (default: all)",
    )
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    articles = load_articles()
    if args.max_articles is not None:
        articles = articles[: args.max_articles]
    print(f"Loaded {len(articles)} Fox News articles.")
    if not articles:
        print(
            "No Fox News articles found. Ensure current_articles.json or newsapi_articles.json "
            "contains articles with 'foxnews.com' or 'Fox News' in the source field."
        )
    else:
        results = run_analysis(articles)

        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nSaved results: {RESULTS_PATH}")

        text_source_counts = Counter(r["text_source"] for r in results)
        print(f"Text sources used: {dict(text_source_counts)}")

        plot_roberta_sentiment_distribution(results)
        plot_vader_sentiment_distribution(results)
        plot_vader_compound_histogram(results)
        plot_bias_distribution(results)
        plot_sentiment_per_article(results)
        plot_bias_per_article(results)
        print("Done.")
