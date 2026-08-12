from datetime import datetime, timezone

from app.models.events import ParsedEvent
from app.services.call_finder import CallFinder


def test_search_finds_inbound_call():
    event = ParsedEvent(
        timestamp=datetime(
            2026,
            8,
            7,
            6,
            31,
            43,
            tzinfo=timezone.utc,
        ),
        event_name="CHANNEL_CREATE",
        uuid="root-1",
        call_direction="inbound",
        caller_number="+966535125494",
        destination_number="+966115211122",
        data={"variable_sip_h_X-SCUD-TENANT": "aqdamy.com"},
    )
    calls = CallFinder([event]).search(number="00966535125494")
    assert len(calls) == 1
    assert calls[0]["call_id"] == "root-1"
