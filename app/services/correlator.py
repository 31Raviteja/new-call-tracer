from collections import defaultdict

from app.models.events import ParsedEvent


class CallCorrelator:
    """
    Groups FreeSWITCH event legs into calls.

    A call is treated as a connected UUID graph.

    Supported relationships:
    - Channel-Call-UUID
    - Other-Leg-Unique-ID
    - Originating-Leg-UUID
    - variable_originating_leg_uuid
    - Bridge-UUID
    - variable_bridge_uuid
    - Signal-Bond
    - variable_signal_bond
    - CC-Member-Session-UUID
    - variable_cc_member_session_uuid
    - CC-Member-UUID
    - variable_cc_member_uuid
    """

    def __init__(self, events: list[ParsedEvent]):
        self.events = events
        self.events_by_uuid = self._build_event_index()
        self.graph = self._build_graph()

    def _build_event_index(self) -> dict[str, list[ParsedEvent]]:
        index: dict[str, list[ParsedEvent]] = defaultdict(list)

        for event in self.events:
            if not event.uuid:
                continue

            index[event.uuid].append(event)

        return dict(index)

    def _build_graph(self) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = defaultdict(set)

        # Every UUID is a node, even if it has no relationship.
        for event in self.events:
            if event.uuid:
                graph[event.uuid]

        for event in self.events:
            if not event.uuid:
                continue

            related_uuids = self._related_uuids(event)

            for related_uuid in related_uuids:
                if not related_uuid:
                    continue

                if related_uuid == event.uuid:
                    continue

                graph[event.uuid].add(related_uuid)
                graph[related_uuid].add(event.uuid)

        return graph

    @staticmethod
    def _related_uuids(event: ParsedEvent) -> set[str]:
        related: set[str] = set()

        candidates = (
            # Main A-leg/B-leg relationship.
            event.channel_call_uuid,
            event.other_leg_unique_id,
            # Originating/B-leg relationship.
            event.originating_leg_uuid,
            # Bridge relationship.
            event.bridge_uuid,
            # Signal bond relationship.
            event.signal_bond,
            # Queue relationship.
            event.cc_member_session_uuid,
            event.variable_cc_member_session_uuid,
            event.cc_member_uuid,
        )

        for value in candidates:
            if value:
                related.add(value)

        return related

    def correlate(self, root_uuid: str) -> set[str]:
        """
        Return every UUID belonging to the connected call.
        """

        if not root_uuid:
            return set()

        if root_uuid not in self.graph:
            return set()

        visited: set[str] = set()
        stack: list[str] = [root_uuid]

        while stack:
            current_uuid = stack.pop()

            if current_uuid in visited:
                continue

            visited.add(current_uuid)

            for related_uuid in self.graph.get(current_uuid, set()):
                if related_uuid not in visited:
                    stack.append(related_uuid)

        return visited

    def find_root_uuid(self, uuid: str) -> str | None:
        """
        Find the customer/A-leg UUID for a connected call.

        Preference:
        1. inbound channel
        2. channel whose Channel-Call-UUID points to itself
        3. supplied UUID
        """

        related = self.correlate(uuid)

        if not related:
            return None

        candidates: list[ParsedEvent] = []

        for related_uuid in related:
            candidates.extend(self.events_by_uuid.get(related_uuid, []))

        # Prefer inbound legs.
        inbound_events = [
            event
            for event in candidates
            if event.call_direction == "inbound"
            and event.event_name == "CHANNEL_CREATE"
        ]

        if inbound_events:
            inbound_events.sort(
                key=lambda event: (
                    event.event_timestamp if event.event_timestamp is not None else 0
                )
            )
            return inbound_events[0].uuid

        # Prefer an event where Channel-Call-UUID == its own UUID.
        for event in candidates:
            if (
                event.event_name == "CHANNEL_CREATE"
                and event.uuid
                and event.channel_call_uuid == event.uuid
            ):
                return event.uuid

        return uuid
