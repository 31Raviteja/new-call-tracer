from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RawEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    data: dict


class ParsedEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    event_name: str

    uuid: str | None = None
    call_direction: str | None = None

    caller_number: str | None = None
    destination_number: str | None = None

    event_timestamp: int | None = None

    event_subclass: str | None = None
    cc_action: str | None = None
    cc_queue: str | None = None
    cc_agent: str | None = None

    cc_member_uuid: str | None = None
    cc_member_session_uuid: str | None = None

    channel_call_uuid: str | None = None
    other_leg_unique_id: str | None = None
    originating_leg_uuid: str | None = None
    bridge_uuid: str | None = None
    signal_bond: str | None = None
    variable_cc_member_session_uuid: str | None = None

    dtmf_digit: str | None = None
    hangup_cause: str | None = None

    data: dict
