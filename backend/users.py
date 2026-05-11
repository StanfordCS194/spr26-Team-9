import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from redis_client import get_redis

router = APIRouter()

WEEK_S = 7 * 24 * 60 * 60
SESSION_TTL = WEEK_S

VALID_EVENTS = {"search", "article_view", "comparison", "llm_analysis", "session_start", "session_end"}


# ---------- Pydantic models ----------

class CreateUserRequest(BaseModel):
    user_id: str


class EventRequest(BaseModel):
    user_id: str
    session_id: str
    event: str
    payload: dict = {}


# ---------- Helpers ----------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> float:
    return time.time()


# ---------- Routes ----------

@router.post("/api/users", status_code=201)
async def create_user(body: CreateUserRequest):
    r = get_redis()
    key = f"user:{body.user_id}:meta"
    if await r.exists(key):
        raise HTTPException(status_code=409, detail="User already exists")
    now = _now_iso()
    await r.hset(key, mapping={"created_at": now, "last_seen": now})
    return {"user_id": body.user_id, "created_at": now}


@router.get("/api/users/{user_id}")
async def get_user(user_id: str, session_id: str | None = None):
    r = get_redis()
    meta = await r.hgetall(f"user:{user_id}:meta")
    if not meta:
        raise HTTPException(status_code=404, detail="User not found")

    now_ts = _now_ts()
    week_ago = now_ts - WEEK_S

    # All session IDs with their start timestamps
    sessions_raw = await r.zrangebyscore(
        f"user:{user_id}:sessions", week_ago, "+inf", withscores=True
    )
    recent_session_ids = [sid for sid, _ in sessions_raw]

    # KPIs that span all sessions in the last week
    searches_this_week = 0
    return_dates: set[str] = set()
    all_durations: list[float] = []

    # Also collect all-time session durations
    all_session_ids_raw = await r.zrange(f"user:{user_id}:sessions", 0, -1, withscores=True)

    for sid, ts in all_session_ids_raw:
        dur = await r.get(f"session:{sid}:duration")
        if dur is not None:
            all_durations.append(float(dur))

    for sid, ts in sessions_raw:
        events_raw = await r.lrange(f"session:{sid}:events", 0, -1)
        for ev_str in events_raw:
            ev = json.loads(ev_str)
            if ev["event"] == "search":
                searches_this_week += 1
        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        return_dates.add(date_str)

    # Return visits = distinct days with a session, minus the very first session day
    first_session_raw = await r.zrange(f"user:{user_id}:sessions", 0, 0, withscores=True)
    if first_session_raw:
        first_day = datetime.fromtimestamp(first_session_raw[0][1], tz=timezone.utc).date().isoformat()
        return_dates.discard(first_day)
    return_visits_this_week = len(return_dates)

    # Current-session KPIs
    articles_viewed = comparisons = llm_analyses = 0
    if session_id:
        current_events_raw = await r.lrange(f"session:{session_id}:events", 0, -1)
        for ev_str in current_events_raw:
            ev = json.loads(ev_str)
            if ev["event"] == "article_view":
                articles_viewed += 1
            elif ev["event"] == "comparison":
                comparisons += 1
            elif ev["event"] == "llm_analysis":
                llm_analyses += 1

    avg_duration = round(sum(all_durations) / len(all_durations), 1) if all_durations else 0.0

    history = await r.lrange(f"user:{user_id}:search_history", 0, 49)

    return {
        "user_id": user_id,
        "created_at": meta.get("created_at"),
        "kpis": {
            "searches_this_week": searches_this_week,
            "return_visits_this_week": return_visits_this_week,
            "articles_viewed_this_session": articles_viewed,
            "comparison_uses_this_session": comparisons,
            "llm_analyses_this_session": llm_analyses,
            "avg_session_duration_s": avg_duration,
        },
        "search_history": history,
    }


@router.post("/api/events", status_code=204)
async def record_event(body: EventRequest):
    if body.event not in VALID_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unknown event type: {body.event}")

    r = get_redis()
    now_ts = _now_ts()

    # Register session under user (score = creation timestamp)
    await r.zadd(f"user:{body.user_id}:sessions", {body.session_id: now_ts}, nx=True)

    # Append event to session log
    ev_str = json.dumps({"event": body.event, "ts": now_ts, "payload": body.payload})
    await r.rpush(f"session:{body.session_id}:events", ev_str)
    await r.expire(f"session:{body.session_id}:events", SESSION_TTL)

    # Side effects per event type
    if body.event == "search":
        query = body.payload.get("query", "").strip()
        if query:
            await r.lpush(f"user:{body.user_id}:search_history", query)
            await r.ltrim(f"user:{body.user_id}:search_history", 0, 199)

    elif body.event == "session_end":
        duration = body.payload.get("duration_s")
        if duration is not None:
            await r.set(f"session:{body.session_id}:duration", duration, ex=SESSION_TTL)

    # Touch last_seen
    await r.hset(f"user:{body.user_id}:meta", "last_seen", datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat())
