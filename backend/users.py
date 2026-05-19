import time
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from supabase_client import get_supabase

router = APIRouter()

VALID_EVENTS = {"search", "article_view", "comparison", "llm_analysis", "session_end", "new_search"}


# ---------- Pydantic models ----------

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

@router.get("/api/users/{user_id}")
def get_user(user_id: str, session_id: str | None = None):
    sb = get_supabase()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    meta_rows = sb.table("users").select("*").eq("user_id", user_id).limit(1).execute().data
    if not meta_rows:
        raise HTTPException(status_code=404, detail="User not found")
    meta = meta_rows[0]

    searches_result = (
        sb.table("events")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("event", "search")
        .gte("ts", week_ago)
        .execute()
    )
    searches_this_week = searches_result.count or 0

    recent_sessions = (
        sb.table("sessions")
        .select("started_at")
        .eq("user_id", user_id)
        .gte("started_at", week_ago)
        .execute()
        .data or []
    )
    recent_days = {s["started_at"][:10] for s in recent_sessions}
    first_session = (
        sb.table("sessions")
        .select("started_at")
        .eq("user_id", user_id)
        .order("started_at")
        .limit(1)
        .execute()
        .data
    )
    first_session = first_session[0] if first_session else None
    if first_session:
        recent_days.discard(first_session["started_at"][:10])
    return_visits_this_week = len(recent_days)

    durations_result = (
        sb.table("sessions")
        .select("duration_s")
        .eq("user_id", user_id)
        .not_.is_("duration_s", "null")
        .execute()
        .data or []
    )
    durations = [d["duration_s"] for d in durations_result]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

    articles_viewed = comparisons = llm_analyses = 0
    if session_id:
        session_events = (
            sb.table("events")
            .select("event")
            .eq("session_id", session_id)
            .execute()
            .data or []
        )
        for ev in session_events:
            if ev["event"] == "article_view":
                articles_viewed += 1
            elif ev["event"] == "comparison":
                comparisons += 1
            elif ev["event"] == "llm_analysis":
                llm_analyses += 1

    history_rows = (
        sb.table("events")
        .select("payload")
        .eq("user_id", user_id)
        .eq("event", "search")
        .order("ts", desc=True)
        .limit(50)
        .execute()
        .data or []
    )
    history = [r["payload"].get("query", "") for r in history_rows if r["payload"].get("query")]

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
def record_event(body: EventRequest):
    if body.event not in VALID_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unknown event type: {body.event}")

    sb = get_supabase()
    now_iso = _now_iso()

    sb.table("users").upsert(
        {"user_id": body.user_id, "last_seen": now_iso},
        on_conflict="user_id",
        ignore_duplicates=True,
    ).execute()

    sb.table("sessions").upsert(
        {"session_id": body.session_id, "user_id": body.user_id, "started_at": now_iso},
        on_conflict="session_id",
        ignore_duplicates=True,
    ).execute()

    sb.table("events").insert({
        "session_id": body.session_id,
        "user_id": body.user_id,
        "event": body.event,
        "payload": body.payload,
        "ts": now_iso,
    }).execute()

    if body.event == "session_end":
        duration = body.payload.get("duration_s")
        if duration is not None:
            sb.table("sessions").update({"duration_s": duration}).eq("session_id", body.session_id).execute()

    sb.table("users").update({"last_seen": now_iso}).eq("user_id", body.user_id).execute()
