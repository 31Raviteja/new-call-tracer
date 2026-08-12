from datetime import datetime

from pydantic import BaseModel, Field


class CallStep(BaseModel):
    at: datetime
    step: str
    detail: dict = Field(default_factory=dict)


class CallLeg(BaseModel):
    uuid: str
    role: str
    direction: str | None = None
    destination: str | None = None


class CallSummary(BaseModel):
    ring: float | None = None
    ivr: float | None = None
    queue_wait: float | None = None
    talk: float | None = None
    total: float | None = None


class CallHistory(BaseModel):
    call_id: str
    tenant: str | None = None
    customer_number: str | None = None
    did: str | None = None
    direction: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    answered: bool = False
    hangup_cause: str | None = None
    legs: list[CallLeg] = Field(default_factory=list)
    timeline: list[CallStep] = Field(default_factory=list)
    recordings: list[str] = Field(default_factory=list)
    durations_sec: CallSummary = Field(default_factory=CallSummary)


class CallSearchResult(BaseModel):
    call_id: str
    uuid: str
    timestamp: datetime
    caller_number: str | None = None
    destination_number: str | None = None
    direction: str | None = None
    tenant: str | None = None


class CallSearchResponse(BaseModel):
    total: int
    results: list[CallSearchResult]


class CallCountResponse(BaseModel):
    count: int | None = None
    group_by: str | None = None
    groups: dict[str, int] | None = None


from pydantic import BaseModel


class ActiveCallResponse(BaseModel):
    root_uuid: str
    event_count: int
    last_event_at: datetime | None = None
