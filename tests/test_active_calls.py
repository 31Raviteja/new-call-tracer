from datetime import datetime, timedelta, timezone

from app.models.events import ParsedEvent
from app.services.active_calls import ActiveCallStore


def make_event(
    uuid: str,
    event_name: str = "CHANNEL_CREATE",
    timestamp: datetime | None = None,
) -> ParsedEvent:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    return ParsedEvent(
        timestamp=timestamp,
        event_name=event_name,
        uuid=uuid,
        data={},
    )


def test_add_and_get_call():
    store = ActiveCallStore()

    event = make_event("call-1")

    call = store.add_event(
        root_uuid="call-1",
        event=event,
    )

    assert call.root_uuid == "call-1"
    assert len(call.events) == 1
    assert store.get("call-1") is call


def test_remove_call():
    store = ActiveCallStore()

    event = make_event("call-1")

    store.add_event(
        root_uuid="call-1",
        event=event,
    )

    removed = store.remove("call-1")

    assert removed is not None
    assert removed.root_uuid == "call-1"
    assert store.get("call-1") is None


def test_remove_stale_calls():
    store = ActiveCallStore()

    now = datetime.now(timezone.utc)

    stale_event = make_event(
        uuid="stale-call",
        timestamp=now - timedelta(seconds=301),
    )

    fresh_event = make_event(
        uuid="fresh-call",
        timestamp=now - timedelta(seconds=100),
    )

    store.add_event(
        root_uuid="stale-call",
        event=stale_event,
    )

    store.add_event(
        root_uuid="fresh-call",
        event=fresh_event,
    )

    stale_calls = store.remove_stale(
        now=now,
        timeout_seconds=300,
    )

    assert len(stale_calls) == 1
    assert stale_calls[0].root_uuid == "stale-call"

    assert store.get("stale-call") is None
    assert store.get("fresh-call") is not None


def test_clear_calls():
    store = ActiveCallStore()

    store.add_event(
        root_uuid="call-1",
        event=make_event("call-1"),
    )

    store.add_event(
        root_uuid="call-2",
        event=make_event("call-2"),
    )

    assert len(store.all()) == 2

    store.clear()

    assert store.all() == []
