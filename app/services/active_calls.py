from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.models.events import ParsedEvent


@dataclass
class ActiveCall:
    root_uuid: str
    events: list[ParsedEvent] = field(default_factory=list)
    last_event_at: datetime | None = None


class ActiveCallStore:
    def __init__(self):
        self._calls: dict[str, ActiveCall] = {}

    def add_event(
        self,
        root_uuid: str,
        event: ParsedEvent,
    ) -> ActiveCall:
        call = self._calls.get(root_uuid)

        if call is None:
            call = ActiveCall(root_uuid=root_uuid)
            self._calls[root_uuid] = call

        call.events.append(event)
        call.last_event_at = event.timestamp

        return call

    def get(self, root_uuid: str) -> ActiveCall | None:
        return self._calls.get(root_uuid)

    def remove(self, root_uuid: str) -> ActiveCall | None:
        return self._calls.pop(root_uuid, None)

    def all(self) -> list[ActiveCall]:
        return list(self._calls.values())

    def remove_stale(
        self,
        now: datetime,
        timeout_seconds: int,
    ) -> list[ActiveCall]:
        cutoff = now - timedelta(seconds=timeout_seconds)

        stale_calls: list[ActiveCall] = []

        for root_uuid, call in list(self._calls.items()):
            if call.last_event_at is not None and call.last_event_at < cutoff:
                stale_calls.append(call)
                del self._calls[root_uuid]

        return stale_calls

    def clear(self) -> None:
        self._calls.clear()


# Shared store used by the API and live event processing.
active_call_store = ActiveCallStore()
