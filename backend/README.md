## `backend/`

FastAPI backend serving article search, user profiles, and KPI telemetry. Runs on Python 3.12+ via Poetry.

---

## Files


| File              | Description                                                                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `main.py`         | FastAPI app entry point. Registers routers, CORS middleware, and pre-warms the BM25 index on startup via the lifespan hook.                               |
| `search.py`       | BM25 article search. Loads `data/articles.json` on startup and re-indexes whenever the file changes (mtime check per request). Exposes `GET /api/search`. |
| `users.py`        | User profiles and event telemetry. Reads/writes Redis. Exposes `POST /api/users`, `GET /api/users/{id}`, `POST /api/events`.                              |
| `redis_client.py` | Async Redis singleton. Reads `REDIS_URL` from the environment; defaults to `redis://localhost:6379`.                                                      |


---

## Running locally

**Prerequisites:** Redis running locally (`brew install redis && brew services start redis`).

```bash
# from backend dir
DATA_PATH=data/articles.json poetry run uvicorn main:app --port 8001 --reload
```

Interactive API docs: `http://localhost:8001/docs`

---

## API

### `GET /api/search`

BM25 keyword search over local articles. Results include a `score` field normalized to [0, 1]; articles scoring below 0.1 are omitted.

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

### `POST /api/channel-summary`

Generate a short AI overview of one source's loaded articles. Requires `OPENAI_API_KEY`.

```json
{
  "source": "New York Times",
  "articles": [
    {
      "title": "...",
      "summary": "...",
      "date": "2026-05-30"
    }
  ]
}
```

### `POST /api/semantic-clusters`

Group loaded articles by semantic similarity using OpenAI embeddings. Requires `OPENAI_API_KEY`.

```json
{
  "articles": [
    {
      "title": "...",
      "description": "..."
    }
  ]
}
```

---

## Environment variables


| Variable    | Default                  | Description               |
| ----------- | ------------------------ | ------------------------- |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string   |
| `DATA_PATH` | `data/articles.json`     | Path to article JSON file |
| `OPENAI_API_KEY` | — | OpenAI API key used for article comparisons, channel summaries, and semantic clustering |


Add both to `.env` (see `.env.example`). For Vercel, provision Upstash Redis from the Marketplace and set `REDIS_URL` in project settings.
