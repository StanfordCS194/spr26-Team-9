"""
NYT article visualizations generated from data/nyt_articles.json.
Run from repo root: python experiments/visualize_nyt.py
"""

import json
import os
from collections import Counter
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "nyt_articles.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "visualizations", "nyt")


def load_articles(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def plot_publication_timeline(articles: list[dict]) -> None:
    """Bar chart of article count per day."""
    dates = [datetime.fromisoformat(a["date"].replace("Z", "+00:00")).date() for a in articles]
    counts = Counter(dates)
    sorted_dates = sorted(counts.keys())
    values = [counts[d] for d in sorted_dates]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(sorted_dates, values, width=0.6, color="#1f77b4")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    plt.xticks(rotation=45, ha="right")
    ax.set_xlabel("Date")
    ax.set_ylabel("Articles Published")
    ax.set_title("NYT Article Publication Timeline")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "publication_timeline.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_top_keywords(articles: list[dict], top_n: int = 20) -> None:
    """Horizontal bar chart of the most frequent keywords across all articles."""
    all_keywords = []
    for a in articles:
        for kw in a.get("keywords", []):
            if kw.get("value"):
                all_keywords.append(kw["value"])

    counts = Counter(all_keywords).most_common(top_n)
    if not counts:
        print("No keywords found.")
        return

    labels, values = zip(*reversed(counts))

    fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.35)))
    ax.barh(labels, values, color="#ff7f0e")
    ax.set_xlabel("Frequency")
    ax.set_title(f"Top {top_n} Keywords in NYT Articles")
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "top_keywords.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")



_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "has", "have", "had", "he", "she", "it", "his", "his", "her",
    "its", "they", "their", "this", "that", "s", "will", "not", "who",
    "what", "how", "about", "after", "over", "into", "than", "more",
}


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
    counts = Counter(cleaned)
    sorted_items = sorted(counts.items(), key=lambda x: x[1])
    labels, values = zip(*sorted_items)

    fig, ax = plt.subplots(figsize=(10, max(3, len(labels) * 0.45)))
    ax.barh(labels, values, color="#9467bd")
    ax.set_xlabel("Number of Articles")
    ax.set_title("NYT Articles per Author")
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "articles_per_author.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_posting_hour_distribution(articles: list[dict]) -> None:
    """Histogram of publication hour (UTC) showing when NYT posts breaking news."""
    hours = [datetime.fromisoformat(a["date"].replace("Z", "+00:00")).hour for a in articles]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.hist(hours, bins=range(25), align="left", color="#17becf", edgecolor="white", rwidth=0.8)
    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Articles Published")
    ax.set_title("NYT Article Posting Hour Distribution")
    ax.set_xticks(range(24))
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "posting_hour_distribution.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_cumulative_coverage(articles: list[dict]) -> None:
    """Step line chart of cumulative article count over time."""
    times = np.array(sorted(datetime.fromisoformat(a["date"].replace("Z", "+00:00")) for a in articles))
    counts = np.arange(1, len(times) + 1)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.step(times, counts, where="post", color="#d62728", linewidth=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d %H:%M"))
    plt.xticks(rotation=45, ha="right")
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative Articles")
    ax.set_title("NYT Cumulative Coverage Over Time")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "cumulative_coverage.png")
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
    ax.barh(labels, values, color="#8c564b")
    ax.set_xlabel("Frequency")
    ax.set_title(f"Top {top_n} Words in NYT Titles & Descriptions")
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "top_title_words.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    articles = load_articles(DATA_PATH)
    print(f"Loaded {len(articles)} articles.")
    plot_publication_timeline(articles)
    plot_top_keywords(articles)
    plot_articles_per_author(articles)
    plot_posting_hour_distribution(articles)
    plot_cumulative_coverage(articles)
    plot_top_title_words(articles)
    print("Done.")
