from datetime import datetime, timezone

from app.models.call_history import (
    CallHistory,
    CallLeg,
    CallStep,
    CallSummary,
)
from app.models.events import ParsedEvent
from app.services.correlator import CallCorrelator


class CallTracer:

    def __init__(self, events: list[ParsedEvent]):
        self.events = events
        self.correlator = CallCorrelator(events)

    def trace(self, root_uuid: str) -> CallHistory | None:

        related_uuids = self.correlator.correlate(root_uuid)

        if not related_uuids:
            return None

        call_events = [
            event
            for event in self.events
            if (
                event.uuid in related_uuids or event.cc_member_session_uuid == root_uuid
            )
        ]

        if not call_events:
            return None

        call_events.sort(
            key=lambda event: (
                event.event_timestamp
                if event.event_timestamp is not None
                else int(event.timestamp.timestamp() * 1_000_000)
            )
        )

        root_events = [event for event in call_events if event.uuid == root_uuid]

        if not root_events:
            return None

        started_at = self._first_event_time(
            root_events,
            "CHANNEL_CREATE",
        )

        ended_at = self._first_event_time(
            root_events,
            "CHANNEL_HANGUP",
        )

        answered_at = self._find_answer_time(
            call_events,
            root_uuid,
        )

        customer_number = self._first_value(
            root_events,
            "caller_number",
        )

        did = self._first_value(
            root_events,
            "destination_number",
        )

        direction = self._first_value(
            root_events,
            "call_direction",
        )

        hangup_cause = self._first_hangup_cause(call_events)

        tenant = self._find_tenant(call_events)

        legs = self._build_legs(call_events)

        timeline = self._build_timeline(call_events)

        recordings = self._find_recordings(call_events)

        durations = self._calculate_durations(
            call_events=call_events,
            started_at=started_at,
            answered_at=answered_at,
            ended_at=ended_at,
        )

        return CallHistory(
            call_id=root_uuid,
            tenant=tenant,
            customer_number=customer_number,
            did=did,
            direction=direction,
            started_at=started_at,
            ended_at=ended_at,
            answered=answered_at is not None,
            hangup_cause=hangup_cause,
            legs=legs,
            timeline=timeline,
            recordings=recordings,
            durations_sec=durations,
        )

    # ---------------------------------------------------------
    # BASIC HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def _first_value(
        events: list[ParsedEvent],
        attribute: str,
    ) -> str | None:

        for event in events:

            value = getattr(
                event,
                attribute,
                None,
            )

            if value:
                return value

        return None

    @staticmethod
    def _first_event_time(
        events: list[ParsedEvent],
        event_name: str,
    ) -> datetime | None:

        for event in events:

            if event.event_name == event_name:
                return event.timestamp

        return None

    # ---------------------------------------------------------
    # ANSWER
    # ---------------------------------------------------------

    @staticmethod
    def _find_answer_time(
        call_events: list[ParsedEvent],
        root_uuid: str,
    ) -> datetime | None:

        for event in call_events:
            if event.event_name != "CHANNEL_ANSWER":
                continue

            return event.timestamp

        return None

    # ---------------------------------------------------------
    # HANGUP
    # ---------------------------------------------------------

    @staticmethod
    def _first_hangup_cause(
        events: list[ParsedEvent],
    ) -> str | None:

        for event in events:
            if event.event_name != "CHANNEL_HANGUP":
                continue

            if event.hangup_cause and event.call_direction == "inbound":
                return event.hangup_cause

        for event in events:
            if event.event_name != "CHANNEL_HANGUP":
                continue

            if event.hangup_cause:
                return event.hangup_cause

        return None

    # ---------------------------------------------------------
    # TENANT
    # ---------------------------------------------------------

    @staticmethod
    def _find_tenant(
        events: list[ParsedEvent],
    ) -> str | None:

        for event in events:
            tenant = event.data.get("variable_sip_h_X-SCUD-TENANT")

            if tenant:
                tenant = str(tenant).strip()

                if tenant and tenant.lower() != "default":
                    return tenant

        for event in events:
            tenant = event.data.get("Caller-Context")

            if tenant:
                tenant = str(tenant).strip()

                if tenant and tenant.lower() != "default":
                    return tenant

        for event in events:
            for field in (
                "Tenant",
                "tenant",
                "variable_tenant",
            ):
                tenant = event.data.get(field)
                if tenant:
                    tenant = str(tenant).strip()

                    if tenant and tenant.lower() != "default":
                        return tenant

        return None

    # ---------------------------------------------------------
    # LEGS
    # ---------------------------------------------------------

    @staticmethod
    def _build_legs(
        events: list[ParsedEvent],
    ) -> list[CallLeg]:

        legs: dict[str, CallLeg] = {}

        for event in events:

            if not event.uuid:
                continue

            if event.uuid in legs:
                continue

            role = "channel"

            if event.cc_agent:
                role = "agent"

            elif event.cc_member_session_uuid:
                role = "queue_member"

            elif event.call_direction == "inbound":
                role = "customer"

            legs[event.uuid] = CallLeg(
                uuid=event.uuid,
                role=role,
                direction=event.call_direction,
                destination=event.destination_number,
            )

        return list(legs.values())

    # ---------------------------------------------------------
    # TIMELINE
    # ---------------------------------------------------------

    @staticmethod
    def _build_timeline(
        events: list[ParsedEvent],
    ) -> list[CallStep]:

        timeline: list[CallStep] = []

        # IMPORTANT:
        # transfer_history is repeated in multiple events.
        # Keep each raw transfer only once.
        seen_transfers: set[str] = set()

        for event in events:

            step = CallTracer._event_to_step(event)

            if step is not None:
                timeline.append(step)

            transfer_steps = CallTracer._transfer_history_steps(
                event,
                seen_transfers,
            )

            timeline.extend(transfer_steps)

        timeline.sort(key=lambda item: item.at)

        return timeline

    # ---------------------------------------------------------
    # NORMAL EVENTS -> TIMELINE
    # ---------------------------------------------------------

    @staticmethod
    def _event_to_step(
        event: ParsedEvent,
    ) -> CallStep | None:

        if event.event_name == "CHANNEL_CREATE":

            return CallStep(
                at=event.timestamp,
                step="channel_create",
                detail={
                    "uuid": event.uuid,
                    "direction": event.call_direction,
                    "destination": event.destination_number,
                },
            )

        if event.event_name == "CHANNEL_ORIGINATE":

            return CallStep(
                at=event.timestamp,
                step="channel_originate",
                detail={
                    "uuid": event.uuid,
                    "destination": event.destination_number,
                },
            )

        if event.event_name == "CHANNEL_ANSWER":

            return CallStep(
                at=event.timestamp,
                step="channel_answer",
                detail={
                    "uuid": event.uuid,
                    "agent": event.cc_agent,
                },
            )

        if event.event_name == "DTMF":

            return CallStep(
                at=event.timestamp,
                step="dtmf",
                detail={
                    "digit": event.dtmf_digit,
                },
            )

        if event.event_name == "RECORD_START":

            return CallStep(
                at=event.timestamp,
                step="record_start",
                detail={
                    "uuid": event.uuid,
                },
            )

        if event.event_name == "CHANNEL_HANGUP":

            return CallStep(
                at=event.timestamp,
                step="channel_hangup",
                detail={
                    "uuid": event.uuid,
                    "cause": event.hangup_cause,
                },
            )

        if event.event_name == "CUSTOM":

            # Ignore empty CUSTOM events.
            if not (
                event.cc_action
                or event.cc_queue
                or event.cc_agent
                or event.cc_member_uuid
                or event.cc_member_session_uuid
            ):
                return None

            return CallTracer._custom_event_to_step(event)

        return None

    # ---------------------------------------------------------
    # CUSTOM / CALLCENTER EVENTS
    # ---------------------------------------------------------

    @staticmethod
    def _custom_event_to_step(
        event: ParsedEvent,
    ) -> CallStep:

        action = (event.cc_action or "").strip()

        action_lower = action.lower()

        detail = {
            "action": event.cc_action,
            "queue": event.cc_queue,
            "agent": event.cc_agent,
            "member_uuid": event.cc_member_uuid,
            "member_session_uuid": (event.cc_member_session_uuid),
        }

        if action_lower == "member-queue-start":

            step = "queue_join"

        elif action_lower == "member-queue-end":

            step = "queue_leave"

        elif action_lower in {
            "agent-offering",
            "agent-offered",
        }:

            step = "agent_offered"

        elif action_lower in {
            "bridge-agent-fail",
            "agent-failed",
        }:

            step = "agent_failed"

        elif action_lower in {
            "bridge-agent-answer",
            "agent-answered",
        }:

            step = "agent_answered"

        elif "menu" in action_lower:

            if "enter" in action_lower or "start" in action_lower:
                step = "menu_enter"

            elif "exit" in action_lower or "end" in action_lower:
                step = "menu_exit"

            else:
                step = "custom"

        else:

            step = "custom"

        return CallStep(
            at=event.timestamp,
            step=step,
            detail=detail,
        )

    # ---------------------------------------------------------
    # TRANSFER HISTORY
    # ---------------------------------------------------------

    @staticmethod
    def _transfer_history_steps(
        event: ParsedEvent,
        seen_transfers: set[str],
    ) -> list[CallStep]:

        raw_history = event.data.get("variable_transfer_history")

        if not raw_history:
            return []

        if isinstance(raw_history, str):
            raw_history = [raw_history]

        if not isinstance(
            raw_history,
            (list, tuple),
        ):
            return []

        steps: list[CallStep] = []

        for item in raw_history:

            if not item:
                continue

            text = str(item).strip()

            if not text:
                continue

            # Prevent duplicates caused by the same
            # transfer history being attached to
            # multiple events.
            if text in seen_transfers:
                continue

            parts = text.split(":")

            if len(parts) < 4:
                continue

            epoch_text = parts[0]

            target = parts[3].split(
                "/",
                1,
            )[0]

            if not target:
                continue

            try:
                epoch = int(epoch_text)

                transfer_time = datetime.fromtimestamp(
                    epoch,
                    tz=timezone.utc,
                ).replace(tzinfo=None)

            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                transfer_time = event.timestamp

            seen_transfers.add(text)

            steps.append(
                CallStep(
                    at=transfer_time,
                    step="transfer",
                    detail={
                        "destination": target,
                        "raw": text,
                    },
                )
            )

        return steps

    # ---------------------------------------------------------
    # RECORDINGS
    # ---------------------------------------------------------

    @staticmethod
    def _find_recordings(
        events: list[ParsedEvent],
    ) -> list[str]:

        recordings: list[str] = []

        for event in events:

            if event.event_name != "RECORD_START":
                continue

            recording = (
                event.data.get("Recording-File-Path")
                or event.data.get("Record-File-Path")
                or event.data.get("variable_recording_file")
                or event.data.get("variable_recording_file_path")
                or event.data.get("variable_recorded_file_1")
            )

            if not recording:
                continue

            recording = str(recording)

            if recording not in recordings:
                recordings.append(recording)

        return recordings

    # ---------------------------------------------------------
    # DURATIONS
    # ---------------------------------------------------------

    @staticmethod
    def _calculate_durations(
        call_events: list[ParsedEvent],
        started_at: datetime | None,
        answered_at: datetime | None,
        ended_at: datetime | None,
    ) -> CallSummary:

        ring = CallTracer._seconds(
            started_at,
            answered_at,
        )

        talk = CallTracer._seconds(
            answered_at,
            ended_at,
        )

        total = CallTracer._seconds(
            started_at,
            ended_at,
        )

        ivr_start = CallTracer._find_step_time(
            call_events,
            "CHANNEL_ANSWER",
        )

        queue_start = CallTracer._find_custom_time(
            call_events,
            "member-queue-start",
        )

        queue_end = CallTracer._find_custom_time(
            call_events,
            "member-queue-end",
        )

        ivr = CallTracer._seconds(
            ivr_start,
            queue_start,
        )

        queue_wait = CallTracer._seconds(
            queue_start,
            queue_end,
        )

        return CallSummary(
            ring=ring,
            ivr=ivr,
            queue_wait=queue_wait,
            talk=talk,
            total=total,
        )

    @staticmethod
    def _find_step_time(
        events: list[ParsedEvent],
        event_name: str,
    ) -> datetime | None:

        for event in events:

            if event.event_name == event_name:
                return event.timestamp

        return None

    @staticmethod
    def _find_custom_time(
        events: list[ParsedEvent],
        action: str,
    ) -> datetime | None:

        for event in events:

            if event.event_name == "CUSTOM" and event.cc_action == action:
                return event.timestamp

        return None

    @staticmethod
    def _seconds(
        start: datetime | None,
        end: datetime | None,
    ) -> float | None:

        if start is None or end is None:
            return None

        value = (end - start).total_seconds()

        if value < 0:
            return None

        return value
