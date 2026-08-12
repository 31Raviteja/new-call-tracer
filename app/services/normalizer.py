from app.models.events import ParsedEvent, RawEvent


class EventNormalizer:
    def normalize(self, event: RawEvent) -> ParsedEvent:
        data = event.data

        return ParsedEvent(
            timestamp=event.timestamp,
            event_name=str(data.get("Event-Name", "")),
            uuid=self._text(data.get("Unique-ID")),
            call_direction=self._text(data.get("Call-Direction")),
            caller_number=self._normalize_number(data.get("Caller-Caller-ID-Number")),
            destination_number=self._normalize_number(
                data.get("Caller-Destination-Number")
            ),
            event_timestamp=self._integer(data.get("Event-Date-Timestamp")),
            event_subclass=self._text(data.get("Event-Subclass")),
            cc_action=self._text(data.get("CC-Action")),
            cc_queue=self._text(data.get("CC-Queue") or data.get("variable_cc_queue")),
            cc_agent=self._text(data.get("CC-Agent") or data.get("variable_cc_agent")),
            cc_member_uuid=self._text(
                data.get("CC-Member-UUID")
                or data.get("variable_cc_member_uuid")
                or data.get("variable_cc_member_pre_answer_uuid")
            ),
            cc_member_session_uuid=self._text(
                data.get("CC-Member-Session-UUID")
                or data.get("variable_cc_member_session_uuid")
            ),
            channel_call_uuid=self._text(
                data.get("variable_channel_call_uuid") or data.get("Channel-Call-UUID")
            ),
            other_leg_unique_id=self._text(
                data.get("Other-Leg-Unique-ID")
                or data.get("variable_other_leg_unique_id")
            ),
            originating_leg_uuid=self._text(
                data.get("Originating-Leg-UUID")
                or data.get("variable_originating_leg_uuid")
            ),
            bridge_uuid=self._text(
                data.get("Bridge-UUID") or data.get("variable_bridge_uuid")
            ),
            signal_bond=self._text(
                data.get("Signal-Bond") or data.get("variable_signal_bond")
            ),
            variable_cc_member_session_uuid=self._text(
                data.get("variable_cc_member_session_uuid")
            ),
            dtmf_digit=self._text(data.get("DTMF-Digit")),
            hangup_cause=self._text(data.get("Hangup-Cause")),
            data=data,
        )

    @staticmethod
    def is_noise(event: ParsedEvent) -> bool:
        if event.event_subclass != "callcenter::info":
            return False
        if event.cc_action not in {
            "agent-status-change",
            "agent-state-change",
            "members-count",
        }:
            return False
        return not event.cc_member_session_uuid

    @staticmethod
    def _text(value) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value if value else None

    @staticmethod
    def _integer(value) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_number(value) -> str | None:
        if value is None:
            return None
        value = str(value).strip().replace("%2B", "+")
        if not value:
            return None
        if value.startswith("00"):
            value = "+" + value[2:]
        if value.startswith("+"):
            return "+" + "".join(c for c in value[1:] if c.isdigit())
        return "".join(c for c in value if c.isdigit())
