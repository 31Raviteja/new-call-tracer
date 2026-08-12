from datetime import datetime, timezone

from app.models.events import ParsedEvent
from app.services.correlator import CallCorrelator
from app.services.normalizer import EventNormalizer


class CallFinder:
    def __init__(self, events: list[ParsedEvent]):
        self.events = events
        self.events_by_uuid = self._build_event_index(events)
        self.events_by_uuid_all = self._build_all_event_index(events)
        self.correlator = CallCorrelator(events)

    @staticmethod
    def _build_all_event_index(
        events: list[ParsedEvent],
    ) -> dict[str, list[ParsedEvent]]:
        index: dict[str, list[ParsedEvent]] = {}

        for event in events:
            if event.uuid:
                index.setdefault(
                    event.uuid,
                    [],
                ).append(event)

        return index

    @staticmethod
    def _build_event_index(
        events: list[ParsedEvent],
    ) -> dict[str, ParsedEvent]:
        index: dict[str, ParsedEvent] = {}

        for event in events:
            if not event.uuid:
                continue

            if event.uuid not in index:
                index[event.uuid] = event
                continue

            current = index[event.uuid]

            # Prefer CHANNEL_CREATE as the representative event.
            if (
                event.event_name == "CHANNEL_CREATE"
                and current.event_name != "CHANNEL_CREATE"
            ):
                index[event.uuid] = event

        return index

    @staticmethod
    def _utc_timestamp(
        value: datetime,
    ) -> datetime:
        """
        Return a timezone-aware UTC datetime.

        If the log timestamp is timezone-naive,
        it is treated as UTC.
        """

        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    def search(
        self,
        number: str | None = None,
        direction: str | None = None,
        tenant: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[dict]:

        normalized_number = (
            EventNormalizer._normalize_number(number)
            if number
            else None
        )

        # Maps root UUID -> representative root event.
        calls: dict[str, ParsedEvent] = {}

        for event in self.events:
            if not event.uuid:
                continue

            # Without a number, discover inbound customer calls.
            if normalized_number is None:
                if (
                    event.event_name != "CHANNEL_CREATE"
                    or event.call_direction != "inbound"
                ):
                    continue

            # With a number, inspect ALL event types.
            elif not self._number_matches(
                event,
                normalized_number,
            ):
                continue

            root_uuid = self.correlator.find_root_uuid(
                event.uuid
            )

            if not root_uuid:
                root_uuid = event.uuid

            root_event = self.events_by_uuid.get(
                root_uuid
            )

            if root_event is None:
                root_event = event

            # Apply direction filter.
            if (
                direction
                and root_event.call_direction != direction
            ):
                continue

            # Apply date filters.
            if (
                date_from
                and root_event.timestamp < date_from
            ):
                continue

            if (
                date_to
                and root_event.timestamp > date_to
            ):
                continue

            event_tenant = self._get_call_tenant(
                root_uuid
            )

            # Apply tenant filter.
            if (
                tenant
                and event_tenant != tenant
            ):
                continue

            calls[root_uuid] = root_event

        results = []

        for root_event in calls.values():

            results.append(
                {
                    "call_id": root_event.uuid,
                    "uuid": root_event.uuid,

                    # UTC timestamp.
                    "timestamp": self._utc_timestamp(
                        root_event.timestamp
                    ),

                    "caller_number": (
                        root_event.caller_number
                    ),

                    "destination_number": (
                        root_event.destination_number
                    ),

                    "direction": (
                        root_event.call_direction
                    ),

                    "tenant": self._get_call_tenant(
                        root_event.uuid
                    ),
                }
            )

        return sorted(
            results,
            key=lambda call: call["timestamp"],
        )

    def _get_call_events(
        self,
        root_uuid: str,
    ) -> list[ParsedEvent]:

        related_uuids = self.correlator.correlate(
            root_uuid
        )

        if not related_uuids:
            return []

        result: list[ParsedEvent] = []

        for uuid in related_uuids:
            result.extend(
                self.events_by_uuid_all.get(
                    uuid,
                    [],
                )
            )

        return result

    def _get_call_tenant(
        self,
        root_uuid: str,
    ) -> str | None:

        events = self._get_call_events(
            root_uuid
        )

        # Primary XLOGIX tenant field.
        for event in events:
            tenant = event.data.get(
                "variable_sip_h_X-SCUD-TENANT"
            )

            if tenant:
                tenant = str(
                    tenant
                ).strip()

                if (
                    tenant
                    and tenant.lower() != "default"
                ):
                    return tenant

        # Caller-Context becomes the tenant domain
        # after transfer into the tenant dialplan.
        for event in events:
            tenant = event.data.get(
                "Caller-Context"
            )

            if tenant:
                tenant = str(
                    tenant
                ).strip()

                if (
                    tenant
                    and tenant.lower() != "default"
                ):
                    return tenant

        # Other explicit tenant fields.
        for event in events:
            for field in (
                "Tenant",
                "tenant",
                "variable_tenant",
            ):
                tenant = event.data.get(
                    field
                )

                if tenant:
                    tenant = str(
                        tenant
                    ).strip()

                    if (
                        tenant
                        and tenant.lower() != "default"
                    ):
                        return tenant

        # Agent domain fallback.
        for event in events:
            if (
                event.cc_agent
                and "@" in event.cc_agent
            ):
                return event.cc_agent.split(
                    "@",
                    1,
                )[1]

        # Queue domain fallback.
        for event in events:
            if (
                event.cc_queue
                and "@" in event.cc_queue
            ):
                return event.cc_queue.split(
                    "@",
                    1,
                )[1]

        return None

    @staticmethod
    def _number_matches(
        event: ParsedEvent,
        normalized_number: str,
    ) -> bool:

        values = [
            event.caller_number,
            event.destination_number,
            event.data.get(
                "Caller-Callee-ID-Number"
            ),
            event.data.get(
                "Caller-Destination-Number"
            ),
            event.data.get(
                "Caller-ANI"
            ),
            event.data.get(
                "variable_sip_req_user"
            ),
            event.data.get(
                "variable_origination_caller_id_number"
            ),
            event.data.get(
                "Other-Leg-Caller-ID-Number"
            ),
            event.data.get(
                "Other-Leg-Destination-Number"
            ),
        ]

        channel_name = event.data.get(
            "Caller-Channel-Name"
        )

        if channel_name:
            values.append(
                channel_name
            )

        for value in values:
            if value is None:
                continue

            normalized_value = (
                EventNormalizer._normalize_number(
                    value
                )
            )

            if (
                normalized_value
                == normalized_number
            ):
                return True

        return False

    # Kept for compatibility with existing code/tests.
    def _root_uuid(
        self,
        event: ParsedEvent,
    ) -> str:

        if not event.uuid:
            return ""

        root_uuid = (
            self.correlator.find_root_uuid(
                event.uuid
            )
        )

        return root_uuid or event.uuid

    @staticmethod
    def _get_tenant(
        event: ParsedEvent,
    ) -> str | None:

        tenant = event.data.get(
            "variable_sip_h_X-SCUD-TENANT"
        )

        if tenant:
            tenant = str(
                tenant
            ).strip()

            if (
                tenant
                and tenant.lower() != "default"
            ):
                return tenant

        tenant = event.data.get(
            "Caller-Context"
        )

        if tenant:
            tenant = str(
                tenant
            ).strip()

            if (
                tenant
                and tenant.lower() != "default"
            ):
                return tenant

        for field in (
            "Tenant",
            "tenant",
            "variable_tenant",
        ):
            tenant = event.data.get(
                field
            )

            if tenant:
                tenant = str(
                    tenant
                ).strip()

                if (
                    tenant
                    and tenant.lower() != "default"
                ):
                    return tenant

        if (
            event.cc_agent
            and "@" in event.cc_agent
        ):
            return event.cc_agent.split(
                "@",
                1,
            )[1]

        if (
            event.cc_queue
            and "@" in event.cc_queue
        ):
            return event.cc_queue.split(
                "@",
                1,
            )[1]

        return None