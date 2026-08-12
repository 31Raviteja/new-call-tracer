from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.models.call_history import (
    ActiveCallResponse,
    CallCountResponse,
    CallHistory,
    CallSearchResponse,
)

from app.services.call_finder import CallFinder
from app.services.correlator import CallCorrelator
from app.services.elasticsearch_locator import ElasticsearchLocator
from app.services.log_reader import LogReader
from app.services.normalizer import EventNormalizer
from app.services.parser import EventParser
from app.services.tracer import CallTracer
from app.services.log_index import LogSearchIndex


router = APIRouter(prefix="/calls", tags=["Calls"])


def _get_elasticsearch_locator() -> ElasticsearchLocator | None:
    if not settings.elasticsearch_url or not settings.elasticsearch_index:
        return None

    try:
        from elasticsearch import Elasticsearch

        client_kwargs = {
            "hosts": [settings.elasticsearch_url],
        }

        if (
            settings.elasticsearch_username
            and settings.elasticsearch_password
        ):
            client_kwargs["basic_auth"] = (
                settings.elasticsearch_username,
                settings.elasticsearch_password,
            )

        client = Elasticsearch(**client_kwargs)

        return ElasticsearchLocator(
            client=client,
            index_name=settings.elasticsearch_index,
        )

    except (ImportError, TypeError, ValueError):
        return None


def load_events(path: str | None = None):
    """
    Full log loader.

    WARNING:
    This reads the complete configured log directory.

    Do NOT use this for normal phone-number searches.
    Number searches must use LogSearchIndex.
    """
    log_dir = Path(path) if path else Path(settings.log_dir)

    if not log_dir.exists() or not log_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Log path does not exist",
        )

    reader = LogReader(log_dir)
    parser = EventParser()
    normalizer = EventNormalizer()

    events = []

    for line in reader.iter_event_lines():
        raw_event = parser.parse(line)

        if raw_event is None:
            continue

        normalized_event = normalizer.normalize(raw_event)

        if normalizer.is_noise(normalized_event):
            continue

        events.append(normalized_event)

    return events


def locate_with_elasticsearch(number: str) -> list[str]:
    """
    Optional Elasticsearch locator.
    """
    locator = _get_elasticsearch_locator()

    if locator is None:
        return []

    try:
        return list(locator.locate(number))
    except (ConnectionError, TimeoutError, ValueError):
        return []


@router.get("/search", response_model=CallSearchResponse)
def search_calls(
    number: str | None = None,
    direction: str | None = None,
    tenant: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    path: str | None = None,
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
    """
    Search calls.

    When a phone number is supplied without a custom path,
    use the SQLite index instead of scanning the complete
    log directory.
    """

    # ============================================================
    # FAST PHONE NUMBER SEARCH
    # ============================================================

    if number and not path:

        index = LogSearchIndex()

        # --------------------------------------------------------
        # 1. Find UUIDs from the indexed phone number
        # --------------------------------------------------------

        uuids = index.search_uuids(number)

        if not uuids:
            return {
                "total": 0,
                "results": [],
            }

        # --------------------------------------------------------
        # 2. Read only events belonging to those UUIDs
        # --------------------------------------------------------

        matching_events = index.read_events(uuids)

        if not matching_events:
            return {
                "total": 0,
                "results": [],
            }

        # --------------------------------------------------------
        # 3. Reconstruct calls
        # --------------------------------------------------------

        finder = CallFinder(matching_events)

        calls = finder.search(
            number=number,
            direction=direction,
            tenant=tenant,
            date_from=date_from,
            date_to=date_to,
        )

        # --------------------------------------------------------
        # 4. Pagination
        # --------------------------------------------------------

        total = len(calls)

        paginated_calls = calls[
            offset:offset + limit
        ]

        return {
            "total": total,
            "results": paginated_calls,
        }

    # ============================================================
    # CUSTOM PATH SEARCH
    # ============================================================

    if path:

        events = load_events(path)

        calls = CallFinder(events).search(
            number=number,
            direction=direction,
            tenant=tenant,
            date_from=date_from,
            date_to=date_to,
        )

        total = len(calls)

        return {
            "total": total,
            "results": calls[
                offset:offset + limit
            ],
        }

    # ============================================================
    # DEFAULT SEARCH
    # ============================================================

    events = load_events()

    calls = CallFinder(events).search(
        number=number,
        direction=direction,
        tenant=tenant,
        date_from=date_from,
        date_to=date_to,
    )

    total = len(calls)

    return {
        "total": total,
        "results": calls[
            offset:offset + limit
        ],
    }


@router.get(
    "/count",
    response_model=CallCountResponse,
)
def count_calls(
    path: str | None = None,
    group_by: str | None = Query(
        default=None,
        description=(
            "Optional grouping: "
            "did, tenant, hangup_cause, or hour"
        ),
    ),
):
    """
    Count calls.

    NOTE:
    This endpoint without additional indexed filtering
    can require reading the complete log dataset.
    """

    events = load_events(path)

    calls = CallFinder(events).search()

    if not group_by:
        return {
            "count": len(calls),
        }

    allowed_groups = {
        "did",
        "tenant",
        "hangup_cause",
        "hour",
    }

    if group_by not in allowed_groups:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid group_by. "
                "Use one of: "
                "did, tenant, hangup_cause, hour"
            ),
        )

    values = []

    if group_by == "did":
        values = [
            call["destination_number"]
            for call in calls
            if call.get("destination_number")
        ]

    elif group_by == "tenant":
        values = [
            call["tenant"]
            for call in calls
            if call.get("tenant")
        ]

    elif group_by == "hangup_cause":
        tracer = CallTracer(events)

        for call in calls:
            history = tracer.trace(
                call["call_id"]
            )

            if history and history.hangup_cause:
                values.append(
                    history.hangup_cause
                )

    elif group_by == "hour":
        values = [
            call["timestamp"].strftime(
                "%Y-%m-%d %H:00"
            )
            for call in calls
            if call.get("timestamp")
        ]

    return {
        "count": None,
        "group_by": group_by,
        "groups": dict(Counter(values)),
    }


@router.get(
    "/history",
    response_model=list[CallHistory],
)
def get_call_history(
    number: str,
    path: str | None = None,
):
    """
    Get call history for a number.

    Uses the SQLite index when no custom path is supplied.
    """

    # ============================================================
    # FAST INDEXED HISTORY SEARCH
    # ============================================================
    if not path:

        index = LogSearchIndex()

        uuids = index.search_uuids(number)

        if not uuids:
            raise HTTPException(
                status_code=404,
                detail="No calls found for this number",
            )

        related_uuids = index.related_uuids(
            uuids
        )

        if not related_uuids:
            related_uuids = uuids

        events = index.read_events(
            related_uuids
        )

    # ============================================================
    # CUSTOM PATH
    # ============================================================
    else:
        events = load_events(path)

    calls = CallFinder(events).search(
        number=number
    )

    if not calls:
        raise HTTPException(
            status_code=404,
            detail="No calls found for this number",
        )

    tracer = CallTracer(events)

    histories = [
        history
        for history in (
            tracer.trace(call["call_id"])
            for call in calls
        )
        if history is not None
    ]

    if not histories:
        raise HTTPException(
            status_code=404,
            detail=(
                "Call history could not be reconstructed"
            ),
        )

    return histories

@router.get(
    "/{call_id}",
    response_model=CallHistory,
)
def get_call(
    call_id: str,
    path: str | None = None,
):
    """
    Get one call by UUID.

    Uses indexed events when possible.
    """

    # ============================================================
    # FAST INDEXED CALL LOOKUP
    # ============================================================
    if not path:

        index = LogSearchIndex()

        # Find the requested UUID and related UUIDs.
        related_uuids = index.related_uuids(
            {call_id}
        )

        if not related_uuids:
            related_uuids = {call_id}

        events = index.read_events(
            related_uuids
        )

    else:
        events = load_events(path)

    history = CallTracer(events).trace(
        call_id
    )

    if history is None:
        raise HTTPException(
            status_code=404,
            detail="Call not found",
        )

    return history