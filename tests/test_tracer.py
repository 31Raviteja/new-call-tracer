from datetime import datetime, timezone

from app.services.tracer import CallTracer


def test_duration_math():
    start = datetime(
        2026,
        8,
        7,
        6,
        31,
        43,
        tzinfo=timezone.utc,
    )

    answered = datetime(
        2026,
        8,
        7,
        6,
        31,
        45,
        500000,
        tzinfo=timezone.utc,
    )

    ended = datetime(
        2026,
        8,
        7,
        6,
        32,
        15,
        500000,
        tzinfo=timezone.utc,
    )

    assert CallTracer._seconds(start, answered) == 2.5
    assert CallTracer._seconds(answered, ended) == 30.0
    assert CallTracer._seconds(start, ended) == 32.5


def test_duration_math_returns_none_for_missing_timestamp():
    timestamp = datetime(
        2026,
        8,
        7,
        6,
        31,
        43,
        tzinfo=timezone.utc,
    )

    assert CallTracer._seconds(None, timestamp) is None
    assert CallTracer._seconds(timestamp, None) is None


def test_duration_math_returns_none_for_negative_duration():
    start = datetime(
        2026,
        8,
        7,
        6,
        31,
        45,
        tzinfo=timezone.utc,
    )

    end = datetime(
        2026,
        8,
        7,
        6,
        31,
        43,
        tzinfo=timezone.utc,
    )

    assert CallTracer._seconds(start, end) is None
