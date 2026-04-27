"""
NYT article visualizations generated from data/nyt_articles.json.
Run from repo root: python experiments/visualize_nyt.py
"""

import json
import os
from collections import Counter
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "nyt_articles.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "visualizations")


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


def plot_articles_by_section(articles: list[dict]) -> None:
    """Horizontal bar chart of article counts grouped by news_desk."""
    counts = Counter(a.get("news_desk", "Unknown") for a in articles)
    sorted_items = sorted(counts.items(), key=lambda x: x[1])
    labels, values = zip(*sorted_items)

    fig, ax = plt.subplots(figsize=(8, max(3, len(labels) * 0.45)))
    ax.barh(labels, values, color="#2ca02c")
    ax.set_xlabel("Number of Articles")
    ax.set_title("NYT Articles by News Desk")
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "articles_by_section.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    articles = load_articles(DATA_PATH)
    print(f"Loaded {len(articles)} articles.")
    plot_publication_timeline(articles)
    plot_top_keywords(articles)
    plot_articles_by_section(articles)
    print("Done.")
