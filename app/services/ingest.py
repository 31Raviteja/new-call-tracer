from app.models.call_history import CallHistory
from app.models.events import ParsedEvent
from app.services.call_finder import CallFinder
from app.services.tracer import CallTracer


def build_histories(
    events: list[ParsedEvent],
) -> list[CallHistory]:

    finder = CallFinder(events)
    tracer = CallTracer(events)

    root_uuids: set[str] = set()

    for event in events:
        if event.event_name != "CHANNEL_CREATE":
            continue

        if not event.uuid:
            continue

        root_uuids.add(finder._root_uuid(event))

    histories: list[CallHistory] = []

    for root_uuid in sorted(root_uuids):
        history = tracer.trace(root_uuid)

        if history is not None:
            histories.append(history)

    return sorted(
        histories,
        key=lambda history: (
            history.started_at or history.ended_at,
            history.call_id,
        ),
    )
