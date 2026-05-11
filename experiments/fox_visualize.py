"""
Fox News article visualizations generated from data/current_articles.json and
data/newsapi_articles.json. Filters for Fox News articles by source domain/name.
Run from repo root: python experiments/visualize_fox.py
"""

import json
import os
from collections import Counter
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

CURRENTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "current_articles.json")
NEWSAPI_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "newsapi_articles.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "visualizations", "fox")

_FOX_IDENTIFIERS = {"foxnews.com", "fox news", "fox business", "foxbusiness.com"}


def _is_fox(article: dict) -> bool:
    """Return True if the article's source is Fox News."""
    source = (article.get("source") or "").lower()
    return any(ident in source for ident in _FOX_IDENTIFIERS)


def _parse_date(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def load_articles() -> list[dict]:
    """Load and merge CurrentsAPI and NewsAPI data, filtering to Fox News articles."""
    articles = []
    for path in (CURRENTS_PATH, NEWSAPI_PATH):
        with open(path, "r", encoding="utf-8") as f:
            articles.extend(json.load(f))
    fox = [a for a in articles if _is_fox(a)]
    return fox


_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "has", "have", "had", "he", "she", "it", "his", "her",
    "its", "they", "their", "this", "that", "s", "will", "not", "who",
    "what", "how", "about", "after", "over", "into", "than", "more",
}


def plot_publication_timeline(articles: list[dict]) -> None:
    """Bar chart of article count per day."""
    dates = [_parse_date(a["date"]).date() for a in articles]
    counts = Counter(dates)
    sorted_dates = sorted(counts.keys())
    values = [counts[d] for d in sorted_dates]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(sorted_dates, values, width=0.6, color="#c0392b")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    plt.xticks(rotation=45, ha="right")
    ax.set_xlabel("Date")
    ax.set_ylabel("Articles Published")
    ax.set_title("Fox News Article Publication Timeline")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_publication_timeline.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_top_sources(articles: list[dict], top_n: int = 20) -> None:
    """Horizontal bar chart of the most frequent sources across all articles."""
    sources = [a.get("source") or "Unknown" for a in articles]
    counts = Counter(sources).most_common(top_n)
    if not counts:
        print("No source data found.")
        return

    labels, values = zip(*reversed(counts))

    fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.35)))
    ax.barh(labels, values, color="#e67e22")
    ax.set_xlabel("Article Count")
    ax.set_title(f"Top {top_n} Sources in Fox News Dataset")
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_top_sources.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def _format_author(raw: str) -> str:
    """Return 'First Author (+N others)' for bylines with multiple authors."""
    raw = raw.removeprefix("By ").strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) > 1:
        return f"{parts[0]} (+{len(parts) - 1} others)"
    return raw


def plot_articles_per_author(articles: list[dict]) -> None:
    """Horizontal bar chart of article count per author."""
    cleaned = [_format_author(a["author"]) for a in articles if a.get("author")]
    if not cleaned:
        print("No author data found.")
        return
    counts = Counter(cleaned)
    sorted_items = sorted(counts.items(), key=lambda x: x[1])
    labels, values = zip(*sorted_items)

    fig, ax = plt.subplots(figsize=(10, max(3, len(labels) * 0.45)))
    ax.barh(labels, values, color="#8e44ad")
    ax.set_xlabel("Number of Articles")
    ax.set_title("Fox News Articles per Author")
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_articles_per_author.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_posting_hour_distribution(articles: list[dict]) -> None:
    """Histogram of publication hour (UTC) showing when Fox News posts breaking news."""
    hours = [_parse_date(a["date"]).hour for a in articles]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.hist(hours, bins=range(25), align="left", color="#16a085", edgecolor="white", rwidth=0.8)
    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Articles Published")
    ax.set_title("Fox News Article Posting Hour Distribution")
    ax.set_xticks(range(24))
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_posting_hour_distribution.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_cumulative_coverage(articles: list[dict]) -> None:
    """Step line chart of cumulative article count over time."""
    times = sorted(_parse_date(a["date"]) for a in articles)
    times_num = [mdates.date2num(t) for t in times]
    counts = list(range(1, len(times_num) + 1))

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.step(times_num, counts, where="post", color="#e74c3c", linewidth=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d %H:%M"))
    plt.xticks(rotation=45, ha="right")
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative Articles")
    ax.set_title("Fox News Cumulative Coverage Over Time")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_cumulative_coverage.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_top_title_words(articles: list[dict], top_n: int = 20) -> None:
    """Horizontal bar chart of the most frequent meaningful words in titles and descriptions."""
    words = []
    for a in articles:
        text = f"{a.get('title', '')} {a.get('description', '')}"
        words.extend(
            w for w in text.lower().split()
            if w.isalpha() and w not in _STOPWORDS and len(w) > 2
        )

    counts = Counter(words).most_common(top_n)
    if not counts:
        print("No words found.")
        return

    labels, values = zip(*reversed(counts))
    fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.35)))
    ax.barh(labels, values, color="#7f5345")
    ax.set_xlabel("Frequency")
    ax.set_title(f"Top {top_n} Words in Fox News Titles & Descriptions")
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_top_title_words.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    articles = load_articles()
    print(f"Loaded {len(articles)} Fox News articles.")
    if not articles:
        print(
            "No Fox News articles found. Ensure current_articles.json or newsapi_articles.json "
            "contains articles with 'foxnews.com' or 'Fox News' in the source field."
        )
    else:
        plot_publication_timeline(articles)
        plot_top_sources(articles)
        plot_articles_per_author(articles)
        plot_posting_hour_distribution(articles)
        plot_cumulative_coverage(articles)
        plot_top_title_words(articles)
        print("Done.")
