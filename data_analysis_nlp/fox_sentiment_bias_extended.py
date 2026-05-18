"""
Extended sentiment and political-bias analysis of Fox News articles.

Builds on fox_sentiment_bias.py with 7 additional analyses:
  1. Sentiment over time (daily mean + article volume)
  2. Headline vs body sentiment delta
  3. Charged language frequency
  4. Top named entities (spaCy NER) + sentiment-when-mentioned
  5. Bias x sentiment scatter
  6. Author sentiment/bias breakdown
  7. Sentence-level sentiment trajectories

All scraping and NLP results are cached to disk; re-runs only regenerate charts.

Run from repo root: python experiments/fox_sentiment_bias_extended.py
"""

import json
import os
import re
import textwrap
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import numpy as np
import trafilatura
from dateutil import parser as dateparser
from transformers import pipeline
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_DIR = os.path.dirname(__file__)
CURRENTS_PATH = os.path.join(_DIR, "..", "data", "current_articles.json")
NEWSAPI_PATH = os.path.join(_DIR, "..", "data", "newsapi_articles.json")
OUT_DIR = os.path.join(_DIR, "..", "visualizations", "fox")
RESULTS_PATH = os.path.join(_DIR, "..", "data", "fox_sentiment_bias.json")
SCRAPED_TEXT_PATH = os.path.join(_DIR, "..", "data", "fox_scraped_text.json")
TITLE_SENTIMENT_PATH = os.path.join(_DIR, "..", "data", "fox_title_sentiment.json")
SENTENCE_SENTIMENT_PATH = os.path.join(_DIR, "..", "data", "fox_sentence_sentiment.json")

_FOX_IDENTIFIERS = {"foxnews.com", "fox news", "fox business", "foxbusiness.com"}

ROBERTA_COLORS = {"positive": "#38b86b", "neutral": "#f0a500", "negative": "#d62728"}
BIAS_COLORS = {"Left": "#4f9eea", "Center": "#2ca02c", "Right": "#d62728"}

_BIAS_LABEL_MAP = {
    "LABEL_0": "Left",
    "LABEL_1": "Center",
    "LABEL_2": "Right",
    "0": "Left",
    "1": "Center",
    "2": "Right",
}

CHARGED_LEXICON = [
    "slammed", "blasted", "radical", "shocking", "outrageous", "destroyed",
    "attacked", "failed", "crisis", "disaster", "corrupt", "lies", "hoax",
    "extreme", "dangerous", "invasion", "threat", "devastating", "chaos", "alarming",
]


def _normalize_bias_label(raw: str) -> str:
    label = _BIAS_LABEL_MAP.get(raw, raw)
    return label.capitalize()


def signed_roberta(label: str, score: float) -> float:
    """Convert RoBERTa label+score to signed float: positive→+score, negative→−score, neutral→0."""
    if label == "positive":
        return score
    if label == "negative":
        return -score
    return 0.0


def signed_bias(label: str, score: float) -> float:
    """Convert bias label+score to signed float: Right→+score, Left→−score, Center→0."""
    if label == "Right":
        return score
    if label == "Left":
        return -score
    return 0.0


# ---------------------------------------------------------------------------
# Data loading (unchanged from fox_sentiment_bias.py)
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
# Text scraping (unchanged from fox_sentiment_bias.py)
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
# NLP analysis (unchanged from fox_sentiment_bias.py, with added result cache)
# ---------------------------------------------------------------------------

def _vader_label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def run_analysis(articles: list[dict]) -> list[dict]:
    """
    Scrape article text and run all three NLP models. Two-level cache:
      Level 1 (scraped text):  data/fox_scraped_text.json
      Level 2 (NLP results):   data/fox_sentiment_bias.json
    """
    if os.path.exists(RESULTS_PATH):
        print(f"\nLoading cached NLP results from {RESULTS_PATH}...")
        with open(RESULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

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
            "text": body,
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


def _enrich_with_text(results: list[dict]) -> list[dict]:
    """Attach scraped body text to results loaded from cache (which may predate the text field)."""
    if all("text" in r and r["text"] for r in results):
        return results
    if not os.path.exists(SCRAPED_TEXT_PATH):
        return results
    with open(SCRAPED_TEXT_PATH, "r", encoding="utf-8") as f:
        scraped_records = json.load(f)
    url_to_text = {r["url"]: r["text"] for r in scraped_records}
    for r in results:
        if not r.get("text"):
            r["text"] = url_to_text.get(r["url"], r.get("title", ""))
    return results


# ---------------------------------------------------------------------------
# New NLP helpers (cached)
# ---------------------------------------------------------------------------

def run_title_sentiment(results: list[dict], roberta_pipe) -> dict:
    """
    Run RoBERTa on article titles. Returns {url: {label, score}}.
    Cached at data/fox_title_sentiment.json.
    """
    if os.path.exists(TITLE_SENTIMENT_PATH):
        print(f"Loading cached title sentiment from {TITLE_SENTIMENT_PATH}...")
        with open(TITLE_SENTIMENT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"\nRunning RoBERTa on {len(results)} titles...")
    titles = [r["title"] for r in results]
    raw = roberta_pipe(titles, batch_size=4, truncation=True, max_length=512)
    title_sents = {
        r["url"]: {"label": res["label"].lower(), "score": round(res["score"], 4)}
        for r, res in zip(results, raw)
    }
    with open(TITLE_SENTIMENT_PATH, "w", encoding="utf-8") as f:
        json.dump(title_sents, f, indent=2, ensure_ascii=False)
    print(f"Saved title sentiment: {TITLE_SENTIMENT_PATH}")
    return title_sents


def run_sentence_sentiment(results: list[dict], roberta_pipe, n: int = 5) -> dict:
    """
    Run RoBERTa sentence-by-sentence on the n longest fully-scraped articles.
    Returns {url: [{sentence, label, score}]}.
    Cached at data/fox_sentence_sentiment.json.
    """
    if os.path.exists(SENTENCE_SENTIMENT_PATH):
        print(f"Loading cached sentence sentiment from {SENTENCE_SENTIMENT_PATH}...")
        with open(SENTENCE_SENTIMENT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    import nltk
    nltk.download("punkt", quiet=True)
    nltk.download("punkt_tab", quiet=True)
    from nltk.tokenize import sent_tokenize

    candidates = [r for r in results if r.get("text_source") == "scraped" and r.get("text")]
    candidates.sort(key=lambda r: len(r.get("text", "")), reverse=True)
    selected = candidates[:n]

    sentence_data = {}
    for r in selected:
        print(f"  Sentence sentiment: {r['title'][:60]}...")
        sentences = [s.strip() for s in sent_tokenize(r["text"]) if len(s.strip()) > 20]
        if not sentences:
            continue
        raw = roberta_pipe(sentences, batch_size=8, truncation=True, max_length=128)
        sentence_data[r["url"]] = [
            {"sentence": s, "label": res["label"].lower(), "score": round(res["score"], 4)}
            for s, res in zip(sentences, raw)
        ]

    with open(SENTENCE_SENTIMENT_PATH, "w", encoding="utf-8") as f:
        json.dump(sentence_data, f, indent=2, ensure_ascii=False)
    print(f"Saved sentence sentiment: {SENTENCE_SENTIMENT_PATH}")
    return sentence_data


# ---------------------------------------------------------------------------
# Original visualizations (unchanged from fox_sentiment_bias.py)
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
# New visualizations (7 additional analyses)
# ---------------------------------------------------------------------------

def plot_sentiment_over_time(results: list[dict]) -> None:
    """
    Daily mean signed RoBERTa + VADER compound as lines (left axis),
    article volume as bars (right axis).
    """
    daily_roberta: dict = defaultdict(list)
    daily_vader: dict = defaultdict(list)

    for r in results:
        raw_date = r.get("date", "")
        if not raw_date:
            continue
        try:
            day = dateparser.parse(raw_date).date()
        except Exception:
            continue
        daily_roberta[day].append(signed_roberta(r["roberta_label"], r["roberta_score"]))
        daily_vader[day].append(r["vader_compound"])

    if not daily_roberta:
        print("Skipping sentiment over time: no valid dates found.")
        return

    days = sorted(daily_roberta.keys())
    mean_roberta = [np.mean(daily_roberta[d]) for d in days]
    mean_vader = [np.mean(daily_vader[d]) for d in days]
    volume = [len(daily_roberta[d]) for d in days]
    x = list(range(len(days)))
    day_labels = [str(d) for d in days]

    fig, ax1 = plt.subplots(figsize=(max(8, len(days) * 1.2), 5))
    ax2 = ax1.twinx()

    ax2.bar(x, volume, width=0.4, color="#cccccc", alpha=0.6, label="Article count", zorder=1)
    ax1.plot(x, mean_roberta, "o-", color=ROBERTA_COLORS["positive"], label="RoBERTa signed", zorder=3)
    ax1.plot(x, mean_vader, "s--", color="#f0a500", label="VADER compound", zorder=3)
    ax1.axhline(0, color="black", linewidth=0.8, linestyle=":")

    ax1.set_xticks(x)
    ax1.set_xticklabels(day_labels, rotation=45, ha="right")
    ax1.set_ylabel("Mean Sentiment Score (← Negative   Positive →)")
    ax2.set_ylabel("Article Volume", color="#888888")
    ax2.tick_params(axis="y", labelcolor="#888888")
    ax1.set_title("Fox News Sentiment Over Time")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_sentiment_over_time.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_headline_body_delta(results: list[dict], title_sents: dict) -> None:
    """
    Headline signed score minus body signed score per article (sorted horizontal bars).
    Positive = headline more positive than body; negative = headline more alarming.
    """
    deltas = []
    for r in results:
        ts = title_sents.get(r["url"])
        if ts is None:
            continue
        delta = round(
            signed_roberta(ts["label"], ts["score"])
            - signed_roberta(r["roberta_label"], r["roberta_score"]),
            4,
        )
        deltas.append((textwrap.shorten(r["title"], width=55, placeholder="…"), delta))

    if not deltas:
        print("Skipping headline/body delta: no matching data.")
        return

    deltas.sort(key=lambda x: x[1])
    labels, values = zip(*deltas)
    colors = ["#d62728" if v < 0 else "#38b86b" for v in values]

    fig, ax = plt.subplots(figsize=(12, max(4, len(labels) * 0.38)))
    ax.barh(list(labels), list(values), color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("← Headline more negative     Headline more positive →")
    ax.set_title("Fox News Headline vs Body Sentiment Delta (RoBERTa)")
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_headline_body_delta.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_charged_language(results: list[dict]) -> None:
    """Horizontal bar of curated charged-word total occurrences across all article bodies."""
    word_counts: Counter = Counter()
    for r in results:
        body = r.get("text", "")
        for word in CHARGED_LEXICON:
            word_counts[word] += len(re.findall(r"\b" + re.escape(word) + r"\b", body, re.IGNORECASE))

    present = [(w, c) for w, c in word_counts.items() if c > 0]
    if not present:
        print("Skipping charged language: no lexicon matches found in article bodies.")
        return

    present.sort(key=lambda x: x[1], reverse=True)
    words, counts = zip(*present)

    fig, ax = plt.subplots(figsize=(10, max(4, len(words) * 0.4)))
    ax.barh(list(words), list(counts), color="#d62728")
    ax.set_xlabel("Total Occurrences Across All Articles")
    ax.set_title("Fox News Charged Language Frequency")
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_charged_language.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_named_entities(results: list[dict]) -> None:
    """
    Two subplots:
      Left:  top 15 PERSON + ORG entities by mention count.
      Right: top 10 PERSON entities by mean signed RoBERTa score (articles mentioning them).
    Requires spaCy with en_core_web_sm.
    """
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
    except (ImportError, OSError):
        print("Skipping NER: spacy or en_core_web_sm not available. Install with:")
        print("  pip install spacy && python -m spacy download en_core_web_sm")
        return

    entity_counts: Counter = Counter()
    person_sentiments: dict[str, list[float]] = defaultdict(list)

    for r in results:
        body = r.get("text", "")
        if not body:
            continue
        doc = nlp(body[:100_000])
        seen_persons: set[str] = set()
        for ent in doc.ents:
            if ent.label_ not in ("PERSON", "ORG"):
                continue
            name = ent.text.strip()
            if len(name) < 3:
                continue
            entity_counts[name] += 1
            if ent.label_ == "PERSON" and name not in seen_persons:
                seen_persons.add(name)
                person_sentiments[name].append(
                    signed_roberta(r["roberta_label"], r["roberta_score"])
                )

    if not entity_counts:
        print("Skipping NER: no PERSON or ORG entities found.")
        return

    top_entities = entity_counts.most_common(15)
    ent_names, ent_counts = zip(*top_entities)

    person_means = {
        name: np.mean(scores)
        for name, scores in person_sentiments.items()
        if len(scores) >= 2
    }
    top_persons = sorted(person_means.items(), key=lambda x: x[1])[:10]

    n_rows = max(len(ent_names), max(len(top_persons), 1))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, max(5, n_rows * 0.4)))

    ax1.barh(list(ent_names), list(ent_counts), color="#4f9eea")
    ax1.set_xlabel("Mention Count")
    ax1.set_title("Top Named Entities (PERSON + ORG)")
    ax1.xaxis.set_major_locator(plt.MaxNLocator(integer=True))

    if top_persons:
        p_names, p_means_vals = zip(*top_persons)
        colors = ["#d62728" if v < 0 else "#38b86b" for v in p_means_vals]
        ax2.barh(list(p_names), list(p_means_vals), color=colors)
        ax2.axvline(0, color="black", linewidth=0.8)
        ax2.set_xlabel("Mean Signed Sentiment Score")
        ax2.set_title("Persons: Mean Sentiment When Mentioned (≥2 articles)")
    else:
        ax2.text(0.5, 0.5, "Not enough data\n(need ≥2 articles per person)",
                 ha="center", va="center", transform=ax2.transAxes)
        ax2.set_title("Persons: Mean Sentiment When Mentioned")

    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_named_entities.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_bias_sentiment_scatter(results: list[dict]) -> None:
    """
    One dot per article: x = signed bias, y = signed RoBERTa sentiment.
    Point size proportional to article text length (capped at 800).
    Color by bias label.
    """
    xs, ys, sizes, colors = [], [], [], []
    for r in results:
        xs.append(signed_bias(r["bias_label"], r["bias_score"]))
        ys.append(signed_roberta(r["roberta_label"], r["roberta_score"]))
        sizes.append(max(min(len(r.get("text", "")) / 30, 800), 40))
        colors.append(BIAS_COLORS.get(r["bias_label"], "#aaaaaa"))

    fig, ax = plt.subplots(figsize=(9, 7))
    ax.scatter(xs, ys, s=sizes, c=colors, alpha=0.7, edgecolors="white", linewidths=0.5)
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("← Left bias    Signed Bias Score    Right bias →")
    ax.set_ylabel("← Negative sentiment    Signed RoBERTa    Positive →")
    ax.set_title("Fox News: Bias vs Sentiment per Article\n(point size ∝ article length)")

    handles = [plt.scatter([], [], s=80, color=BIAS_COLORS[l], label=l) for l in ["Left", "Center", "Right"]]
    ax.legend(handles=handles, title="Bias Label")

    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_bias_sentiment_scatter.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_author_breakdown(results: list[dict]) -> None:
    """
    For authors with ≥2 articles: side-by-side horizontal bars of
    mean signed sentiment (left) and mean signed bias (right), sorted by sentiment.
    """
    author_data: dict[str, dict] = defaultdict(lambda: {"sentiments": [], "biases": []})
    for r in results:
        author = (r.get("author") or "").strip()
        if not author or author.lower() in ("unknown", "none", ""):
            continue
        author_data[author]["sentiments"].append(
            signed_roberta(r["roberta_label"], r["roberta_score"])
        )
        author_data[author]["biases"].append(
            signed_bias(r["bias_label"], r["bias_score"])
        )

    qualified = {a: d for a, d in author_data.items() if len(d["sentiments"]) >= 2}
    if not qualified:
        print("Skipping author breakdown: no authors with ≥2 articles.")
        return

    authors = sorted(qualified.keys(), key=lambda a: np.mean(qualified[a]["sentiments"]))
    mean_sent = [np.mean(qualified[a]["sentiments"]) for a in authors]
    mean_bias_vals = [np.mean(qualified[a]["biases"]) for a in authors]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, max(4, len(authors) * 0.5)), sharey=True)

    ax1.barh(authors, mean_sent, color=["#d62728" if v < 0 else "#38b86b" for v in mean_sent])
    ax1.axvline(0, color="black", linewidth=0.8)
    ax1.set_xlabel("Mean Signed Sentiment (RoBERTa)")
    ax1.set_title("Author Sentiment")

    ax2.barh(authors, mean_bias_vals, color=["#4f9eea" if v < 0 else "#d62728" for v in mean_bias_vals])
    ax2.axvline(0, color="black", linewidth=0.8)
    ax2.set_xlabel("Mean Signed Bias (← Left    Right →)")
    ax2.set_title("Author Bias")

    plt.suptitle("Fox News Author Breakdown (authors with ≥2 articles)", y=1.01)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_author_breakdown.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved: {out}")


def plot_sentence_trajectories(sentence_data: dict, results: list[dict]) -> None:
    """
    Signed RoBERTa sentiment plotted sentence-by-sentence for each article in sentence_data.
    Green shading above zero, red shading below. Horizontal dashed line at zero.
    """
    if not sentence_data:
        print("Skipping sentence trajectories: no data.")
        return

    url_to_title = {r["url"]: r["title"] for r in results}
    n = len(sentence_data)
    cols = min(n, 2)
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(cols * 8, rows * 3.5), squeeze=False)

    for idx, (url, sentences) in enumerate(sentence_data.items()):
        ax = axes[idx // cols][idx % cols]
        if not sentences:
            ax.set_visible(False)
            continue
        ys = [signed_roberta(s["label"], s["score"]) for s in sentences]
        xs = list(range(1, len(ys) + 1))
        ax.plot(xs, ys, "o-", color="#4f9eea", markersize=4, linewidth=1.5)
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
        ax.fill_between(xs, ys, 0, where=[y > 0 for y in ys], alpha=0.15, color="#38b86b")
        ax.fill_between(xs, ys, 0, where=[y < 0 for y in ys], alpha=0.15, color="#d62728")
        ax.set_xlabel("Sentence Index")
        ax.set_ylabel("Signed Sentiment")
        ax.set_ylim(-1.05, 1.05)
        ax.set_title(
            textwrap.shorten(url_to_title.get(url, url), width=60, placeholder="…"),
            fontsize=9,
        )

    for idx in range(len(sentence_data), rows * cols):
        axes[idx // cols][idx % cols].set_visible(False)

    plt.suptitle("Fox News Sentence-Level Sentiment Trajectories", y=1.01)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "fox_sentence_trajectories.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fox News extended sentiment & bias analysis")
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

        results = _enrich_with_text(results)

        text_source_counts = Counter(r.get("text_source", "unknown") for r in results)
        print(f"Text sources used: {dict(text_source_counts)}")

        # Load RoBERTa only if title or sentence caches are missing
        need_roberta = (
            not os.path.exists(TITLE_SENTIMENT_PATH)
            or not os.path.exists(SENTENCE_SENTIMENT_PATH)
        )
        roberta_pipe = None
        if need_roberta:
            print("\nLoading RoBERTa for extended analyses...")
            roberta_pipe = pipeline(
                "text-classification",
                model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                truncation=True,
                max_length=512,
            )

        title_sents = run_title_sentiment(results, roberta_pipe)
        sentence_data = run_sentence_sentiment(results, roberta_pipe, n=5)

        # Original visualizations
        print("\n--- Original visualizations ---")
        plot_roberta_sentiment_distribution(results)
        plot_vader_sentiment_distribution(results)
        plot_vader_compound_histogram(results)
        plot_bias_distribution(results)
        plot_sentiment_per_article(results)
        plot_bias_per_article(results)

        # New visualizations
        print("\n--- Extended visualizations ---")
        plot_sentiment_over_time(results)
        plot_headline_body_delta(results, title_sents)
        plot_charged_language(results)
        plot_named_entities(results)
        plot_bias_sentiment_scatter(results)
        plot_author_breakdown(results)
        plot_sentence_trajectories(sentence_data, results)

        print("\nDone.")
