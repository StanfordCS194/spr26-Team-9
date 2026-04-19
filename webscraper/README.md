# Webscraper

Data ingestion pipeline for the LLM & Media Bias Tracker. Fetches news articles from external APIs, normalizes them into a common format, and saves results to `data/` at the repo root.

---

## Files

### `api_keys.py`
Stores API credentials. Currently holds `NYT_API_KEY` for the New York Times Developer API. This file is listed in `.gitignore` and is never committed to source control.

### `config.py`
Loads configuration for the generic `CurrentAPIAdapter` from a `.env` file in the working directory. Exports two variables:
- `current_api` — API key for the current/generic news API
- `current_url` — Base URL for that API

### `apis.py`
Contains all adapter classes and shared utilities. The adapter pattern means adding a new news source is just adding a new class — `scrape.py` does not need to change.

**`get_meta_description(url)`**
Fetches a URL and extracts its Open Graph (`og:description`) or standard HTML `<meta name="description">` tag. Used to enrich article descriptions beyond what the API returns.

**`CurrentAPIAdapter`**
A generic adapter for a keyword-based news API (configured via `config.py`). Fetches articles by keyword, date range, and domain. Normalizes responses to the standard article format.

**`NYTAdapter`**
Adapter for the [New York Times Article Search API](https://developer.nytimes.com/docs/articlesearch-product/1/overview). Key behaviors:
- Converts ISO 8601 date strings to the `YYYYMMDD` format the NYT API requires
- Sorts results chronologically (`oldest` first) to prevent pagination drift when articles are published mid-run
- Supports pagination via an optional `page` kwarg (each page = 10 articles)
- Captures `lead_paragraph` in addition to the abstract, which contains dense narrative framing useful for NLP analysis

**`ADAPTERS`**
A dictionary mapping adapter names to their classes:
```python
ADAPTERS = {
    "current": CurrentAPIAdapter,
    "nyt":     NYTAdapter,
}
```
To add a new source, implement a class with a `.fetch(query, start, end, **kwargs)` method that returns a list of normalized article dicts, then register it here.

---

### `scrape.py`
Main entry point. Configure the run at the top of the file:

| Variable | Description |
|---|---|
| `QUERY` | Keyword search string (e.g. `"Trump Pope Leo"`) |
| `START` | Start date in ISO 8601 format (`"2026-04-12T00:00:00Z"`) |
| `END` | End date in ISO 8601 format |
| `API` | Adapter to use — any key from `ADAPTERS` (e.g. `"nyt"`) |
| `MAX_PAGES` | Number of pages to fetch (1 page = 10 articles). A 13-second sleep is inserted between pages to comply with the NYT rate limit of 5 requests/minute. |

**What it does:**
1. Instantiates the selected adapter and fetches articles across `MAX_PAGES` pages
2. Prints each article (title, URL, description, date, author) to stdout, enriching descriptions via `get_meta_description()` where possible
3. Loads any previously saved articles from `<repo_root>/data/{API}_articles.json`
4. Deduplicates by URL and appends only new articles, then saves the full list back to JSON

Run from the `webscraper/` directory:
```bash
python scrape.py
```

---

## Normalized Article Format

All adapters return a list of dicts with these fields:

| Field | Source (NYT) |
|---|---|
| `title` | `headline.main` |
| `url` | `web_url` |
| `description` | `abstract` or `snippet` |
| `lead_paragraph` | `lead_paragraph` |
| `date` | `pub_date` |
| `author` | `byline.original` |

---

## Output

Results are saved to `<repo_root>/data/{API}_articles.json` as a JSON array. The `data/` directory is gitignored. Each run appends only articles not already present (deduplicated by URL), so re-running is safe.

---

## Adding a New News Source

1. Create a new adapter class in `apis.py` with a `.fetch(query, start, end, **kwargs)` method
2. Return a list of dicts matching the normalized article format above
3. Register it in the `ADAPTERS` dict
4. Set `API = "<your_adapter_name>"` in `scrape.py` and run
