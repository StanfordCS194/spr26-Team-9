## `backend/`

FastAPI backend serving article search, user profiles, KPI telemetry, and LLM analysis. Runs on Python 3.12+ via uv.

---

## Files

| File                  | Description                                                                                                                                               |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `main.py`             | FastAPI app entry point. Registers routers, CORS middleware, and pre-warms the search cache on startup.                                                   |
| `search.py`           | BM25 article search. Loads `data/articles.json` on startup and re-indexes whenever the file changes (mtime check per request). Exposes `GET /api/search`. |
| `users.py`            | User profiles and event telemetry. Reads/writes Supabase. Exposes `POST /api/users`, `GET /api/users/{id}`, `POST /api/events`.                          |
| `supabase_client.py`  | Supabase singleton. Reads `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from the environment.                                                                 |
| `llm_summary.py`      | LLM analysis pipeline. Queries ChatGPT, Gemini, and Claude in parallel (each with web search grounding), then runs a meta-analysis step with the same model. Results are cached to `data/llm_summaries/` with a 24-hour TTL. Exposes `GET /api/llm-summary`. |
| `compare.py`          | Article comparison. Accepts 2–3 articles and returns an AI-generated side-by-side analysis. Exposes `POST /api/compare`.                                 |
| `channel_summary.py`  | Source coverage summary. Accepts a list of articles from one outlet and returns an AI-generated overview. Exposes `POST /api/channel-summary`.           |
| `bias.py`             | Serves precomputed per-article bias scores from `data/`. Exposes `GET /api/bias`.                                                                        |

---

## Running locally

```bash
# from repo root
uv run uvicorn backend.main:app --port 8000 --reload
```

Or from the `backend/` directory:

```bash
uv run uvicorn main:app --port 8000 --reload
```

Interactive API docs: `http://localhost:8000/docs`

---

## API

### `GET /api/search`

BM25 keyword search over local articles. Triggers the webscraper for the given query if results are not cached. Results include a `score` field normalized to [0, 1].

```
GET /api/search?q=trump+pope&limit=5
```

```json
{
  "query": "trump pope",
  "results": [
    {
      "title": "...",
      "url": "...",
      "description": "...",
      "date": "2026-04-28T20:10:33+00:00",
      "author": "...",
      "source": "cnn.com",
      "score": 0.97
    }
  ]
}
```

### `GET /api/llm-summary`

Queries ChatGPT (`gpt-5.4-mini`), Gemini (`gemini-3.5-flash`), and Claude (`claude-haiku-4-5`) about the given topic in parallel. Each LLM uses web search grounding for step 1 and its own model for the meta-analysis in step 2. Results are cached to `data/llm_summaries/` for 24 hours.

```
GET /api/llm-summary?q=trump+pope
```

```json
{
  "query": "trump pope",
  "generated_at": "2026-05-31T12:00:00Z",
  "llms": [
    {
      "name": "ChatGPT",
      "model": "gpt-5.4-mini",
      "color": "#10a37f",
      "raw_response": "...",
      "summary": "...",
      "biases": [{ "title": "Framing Bias", "body": "..." }],
      "sources": [{ "label": "cnn.com — Title", "url": "https://..." }]
    }
  ]
}
```

### `POST /api/users`

Create a user profile. The frontend generates and owns the UUID.

```json
{ "user_id": "uuid-v4" }
```

Returns `201` on success, `409` if the user already exists.

### `GET /api/users/{user_id}`

Returns the user profile and all KPIs. Pass `?session_id=<uuid>` to get current-session KPIs.

```
GET /api/users/abc-123?session_id=sess-456
```

```json
{
  "user_id": "abc-123",
  "created_at": "2026-05-09T18:00:00+00:00",
  "kpis": {
    "searches_this_week": 12,
    "return_visits_this_week": 3,
    "articles_viewed_this_session": 5,
    "comparison_uses_this_session": 1,
    "llm_analyses_this_session": 0,
    "avg_session_duration_s": 142.0
  },
  "search_history": ["trump pope", "vatican diplomacy"]
}
```

### `POST /api/events`

Record a user action. Fire-and-forget — the frontend does not need to await or handle errors.

```json
{
  "user_id": "abc-123",
  "session_id": "sess-456",
  "event": "search | article_view | comparison | llm_analysis | session_start | session_end",
  "payload": {}
}
```

`session_end` payload: `{ "duration_s": 142 }`.  
`search` payload: `{ "query": "..." }`.  
Returns `204 No Content`.

### `POST /api/compare`

Compare 2–3 articles and return an AI-generated side-by-side analysis. Requires `OPENAI_API_KEY`.

### `POST /api/channel-summary`

Generate a short AI overview of one source's loaded articles. Requires `OPENAI_API_KEY`.

```json
{
  "source": "New York Times",
  "articles": [
    { "title": "...", "summary": "...", "date": "2026-05-30" }
  ]
}
```

---

## Environment variables

| Variable              | Description                                                  |
| --------------------- | ------------------------------------------------------------ |
| `SUPABASE_URL`        | Supabase project URL                                         |
| `SUPABASE_SERVICE_KEY`| Supabase service role key (server-side only)                 |
| `OPENAI_API_KEY`      | Used for search grounding, article comparison, and channel summaries |
| `ANTHROPIC_API_KEY`   | Used for Claude LLM analysis                                 |
| `GOOGLE_API_KEY`      | Used for Gemini LLM analysis                                 |

See `.env.example` at the repo root.
