from datetime import datetime, timezone

from app.models.call_history import CallHistory
from app.models.events import ParsedEvent
from app.services.active_calls import ActiveCallStore
from app.services.correlator import CallCorrelator
from app.services.history_store import HistoryStore
from app.services.kafka_processor import KafkaEventProcessor
from app.services.tracer import CallTracer


class KafkaCallProcessor:
    def __init__(
        self,
        active_calls: ActiveCallStore,
        history_store: HistoryStore,
        timeout_seconds: int = 300,
    ):
        self.active_calls = active_calls
        self.history_store = history_store
        self.timeout_seconds = timeout_seconds
        self.events: list[ParsedEvent] = []
        self.processor = KafkaEventProcessor()

    def process(self, line: str) -> CallHistory | None:
        event = self.processor.process(line)

        if event is None:
            return None

        self.events.append(event)

        if not event.uuid:
            return None

        correlator = CallCorrelator(self.events)
        root_uuid = correlator.find_root_uuid(event.uuid)

        if not root_uuid:
            root_uuid = event.uuid

        self.active_calls.add_event(
            root_uuid=root_uuid,
            event=event,
        )

        if event.event_name != "CHANNEL_HANGUP":
            return None

        related_uuids = correlator.correlate(root_uuid)

        if not related_uuids:
            return None

        call_events = [item for item in self.events if item.uuid in related_uuids]

        if not call_events:
            return None

        active_call = self.active_calls.get(root_uuid)

        if active_call is None:
            return None

        # Wait until every known leg has ended.
        active_uuids = {item.uuid for item in active_call.events if item.uuid}

        hangup_uuids = {
            item.uuid
            for item in call_events
            if item.event_name == "CHANNEL_HANGUP" and item.uuid
        }

        if active_uuids - hangup_uuids:
            return None

        history = CallTracer(self.events).trace(root_uuid)

        if history is None:
            return None

        self.active_calls.remove(root_uuid)

        self.history_store.save(history)

        return history

    def cleanup_stale_calls(
        self,
        now: datetime | None = None,
    ) -> list[ParsedEvent]:
        """
        Remove calls that have not received an event within the timeout.

        Returns the events belonging to calls that were removed.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        stale_calls = self.active_calls.remove_stale(
            now=now,
            timeout_seconds=self.timeout_seconds,
        )

        stale_events: list[ParsedEvent] = []

        for call in stale_calls:
            stale_events.extend(call.events)

        return stale_events
