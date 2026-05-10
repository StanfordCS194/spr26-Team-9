# Backend Implementation Spec

## Overview

A Python REST API serving three concerns: article search, user profile storage, and KPI telemetry. Sits between the frontend and external data sources (`data/articles.json`, NYT/NewsAPI/Currents, and eventually GDELT).

---

## Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Framework | FastAPI | Already Python; async support; auto-generates OpenAPI docs |
| Local search | BM25 (`rank-bm25`) | Better than raw TF-IDF; no model download; scores are interpretable |
| User/KPI store | Redis (prototype) | Low latency; TTL support for session tracking; can swap to Postgres later |
| Deployment | Vercel Python runtime or `uvicorn` locally | Matches current Vercel setup |

---

## API Endpoints

All responses are JSON. All errors return `{"error": "<message>"}` with an appropriate HTTP status.

### Search

#### `GET /api/search`

Search local articles. Backed by BM25 index over `title + description`.

**Query params**

| Param | Type | Required | Description |
|---|---|---|---|
| `q` | string | yes | Natural-language search query |
| `limit` | int | no | Max results (default 10, max 50) |

**Response**
```json
{
  "query": "Trump Pope Leo",
  "results": [
    {
      "title": "...",
      "url": "...",
      "description": "...",
      "date": "2026-04-28T20:10:33+00:00",
      "author": "...",
      "source": "theconversation.com",
      "score": 0.87
    }
  ]
}
```

`score` is BM25 similarity normalized to [0, 1]. Omit articles with `score < 0.1`.

---

### User Profile

#### `POST /api/users`

Create a new user profile. Call once on first visit (frontend generates a UUID).

**Body**
```json
{ "user_id": "uuid-v4" }
```

**Response** `201 Created`
```json
{ "user_id": "uuid-v4", "created_at": "ISO8601" }
```

#### `GET /api/users/{user_id}`

Fetch profile and aggregated KPIs.

**Response**
```json
{
  "user_id": "...",
  "created_at": "ISO8601",
  "kpis": {
    "searches_this_week": 12,
    "return_visits_this_week": 3,
    "articles_viewed_this_session": 5,
    "comparison_uses_this_session": 1,
    "llm_analyses_this_session": 0,
    "avg_session_duration_s": 142
  },
  "search_history": ["Trump Pope Leo", "Vatican diplomacy"]
}
```

---

### Telemetry (KPI events)

#### `POST /api/events`

Record a single user action. Fire-and-forget from the frontend (no need to await or handle errors in the UI).

**Body**
```json
{
  "user_id": "uuid-v4",
  "session_id": "uuid-v4",
  "event": "search | article_view | comparison | llm_analysis | session_start | session_end",
  "payload": {}
}
```

`payload` for `session_end`: `{ "duration_s": 142 }`.  
`payload` for `search`: `{ "query": "..." }`.  
Other events can have an empty payload.

**Response** `204 No Content`

---

## Local Article Search — Implementation

```
data/articles.json  →  build BM25 index on startup  →  serve /api/search
```

1. On startup, load `data/articles.json` and tokenize `title + " " + description` for each article (lowercase, split on whitespace and punctuation).
2. Build a `BM25Okapi` index from `rank-bm25`.
3. Store the raw article list in memory alongside the index (the file is small, ~a few hundred articles, refreshed daily).
4. On query: tokenize the query the same way, call `bm25.get_scores(query_tokens)`, normalize scores by dividing by the max score, filter below 0.1, sort descending, return top `limit`.
5. Reload the index whenever `articles.json` is modified (use `watchfiles` or a simple mtime check on each request).

---

## BigQuery / GDELT Search — Deferred

Skip for prototype. When implemented, add `GET /api/search/gdelt` that accepts the same params and proxies to BigQuery using the `google-cloud-bigquery` client. Keep it a separate endpoint so local and GDELT search are independently callable.

---

## User Profile & KPI Storage — Redis Schema

All keys are prefixed `user:{user_id}`.

| Key | Type | Value | TTL |
|---|---|---|---|
| `user:{id}:meta` | Hash | `created_at`, `last_seen` | none |
| `user:{id}:search_history` | List | query strings, newest first | none |
| `user:{id}:sessions` | Sorted Set | `session_id` → Unix timestamp | none |
| `session:{id}:events` | List | JSON-serialized event objects | 7 days |
| `session:{id}:duration` | String | seconds (int) | 7 days |

**KPI computation** (done at read time in `GET /api/users/{user_id}`):

- `searches_this_week`: count `search` events across all sessions in the last 7 days.
- `return_visits_this_week`: count distinct session dates in the last 7 days (a "return" = any session after the first-ever session).
- `articles_viewed_this_session`: count `article_view` events in the current session.
- `comparison_uses_this_session`: count `comparison` events in the current session.
- `llm_analyses_this_session`: count `llm_analysis` events in the current session.
- `avg_session_duration_s`: mean of `session:{id}:duration` over all completed sessions.

The frontend generates a new `session_id` (UUIDv4) on each page load and sends it with every event. A session ends when the page unloads (`navigator.sendBeacon` → `POST /api/events` with `event: session_end`).

---

## File Structure

```
backend/
  main.py          # FastAPI app, lifespan handler for index init
  search.py        # BM25 index + /api/search handler
  users.py         # /api/users and /api/events handlers
  redis_client.py  # Redis connection singleton
  README.md
  BACKEND.md
```

---

## Environment Variables

```
REDIS_URL=redis://localhost:6379
DATA_PATH=../data/articles.json   # relative to repo root
```

Add to `.env.example`. For Vercel, provision Redis via the Marketplace (Upstash is the standard option) and set `REDIS_URL` in the Vercel project settings.

---

## Out of Scope for Prototype

- Authentication / JWT (use raw `user_id` UUID for now)
- GDELT / BigQuery integration
- Rate limiting
- Persistent article storage beyond the JSON file
