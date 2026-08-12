from datetime import datetime, timezone

from app.models.events import RawEvent
from app.services.normalizer import EventNormalizer


def test_normalize_custom_event():
    event = EventNormalizer().normalize(
        RawEvent(
            timestamp=datetime(
                2026,
                8,
                7,
                6,
                31,
                43,
                tzinfo=timezone.utc,
            ),
            data={
                "Event-Name": "CUSTOM",
                "Event-Subclass": "callcenter::info",
                "CC-Action": "agent-status-change",
            },
        )
    )

    assert event.event_name == "CUSTOM"
    assert event.event_subclass == "callcenter::info"
    assert event.cc_action == "agent-status-change"


def test_normalize_number_formats():
    values = [
        "+966535125494",
        "00966535125494",
        "%2B966535125494",
    ]

    expected = "+966535125494"

    for value in values:
        assert EventNormalizer._normalize_number(value) == expected
