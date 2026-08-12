from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.models.call_history import CallHistory
from app.routers.calls import load_events
from app.services.history_store import HistoryStore
from app.services.ingest import build_histories
from app.services.normalizer import EventNormalizer

router = APIRouter(tags=["History"])


def get_store() -> HistoryStore:
    return HistoryStore(Path(settings.history_db))


def normalize_filter_number(
    value: str | None,
) -> str | None:

    if not value:
        return None

    return EventNormalizer._normalize_number(value)


@router.post("/ingest")
def ingest(path: str | None = None):

    events = load_events(path)

    histories = build_histories(events)

    store = get_store()

    for history in histories:
        store.save(history)

    return {
        "total_found": len(histories),
        "stored": len(histories),
        "database": str(store.db_path),
    }


@router.get("/history/search")
def search_history(
    number: str | None = None,
    did: str | None = None,
    tenant: str | None = None,
    queue: str | None = None,
    agent: str | None = None,
    hangup_cause: str | None = None,
    answered: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_talk_time: float | None = Query(
        default=None,
        ge=0,
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
):

    store = get_store()

    total, histories = store.search(
        number=normalize_filter_number(number),
        did=normalize_filter_number(did),
        tenant=tenant,
        queue=queue,
        agent=agent,
        hangup_cause=hangup_cause,
        answered=answered,
        date_from=date_from,
        date_to=date_to,
        min_talk_time=min_talk_time,
        limit=limit,
        offset=offset,
    )

    results = [
        {
            "call_id": history.call_id,
            "timestamp": history.started_at,
            "customer_number": history.customer_number,
            "did": history.did,
            "direction": history.direction,
            "tenant": history.tenant,
            "answered": history.answered,
            "hangup_cause": history.hangup_cause,
            "talk_time": history.durations_sec.talk,
        }
        for history in histories
    ]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": results,
    }


@router.get(
    "/history/{call_id}",
    response_model=CallHistory,
)
def get_stored_history(call_id: str):

    history = get_store().get(call_id)

    if history is None:
        raise HTTPException(
            status_code=404,
            detail="Stored call history not found",
        )

    return history
