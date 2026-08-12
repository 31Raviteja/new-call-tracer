from datetime import datetime, timezone

from app.models.events import ParsedEvent
from app.services.correlator import CallCorrelator


def make_event(
    uuid: str,
    event_name: str = "CHANNEL_CREATE",
    **kwargs,
) -> ParsedEvent:
    return ParsedEvent(
        timestamp=datetime(
            2026,
            8,
            7,
            6,
            31,
            43,
            tzinfo=timezone.utc,
        ),
        event_name=event_name,
        uuid=uuid,
        data={},
        **kwargs,
    )


def test_correlates_two_leg_call():
    customer = make_event(
        "customer-1",
        call_direction="inbound",
        channel_call_uuid="customer-1",
    )

    agent = make_event(
        "agent-1",
        call_direction="outbound",
        channel_call_uuid="customer-1",
        other_leg_unique_id="customer-1",
    )

    correlator = CallCorrelator([customer, agent])

    assert correlator.correlate("customer-1") == {
        "customer-1",
        "agent-1",
    }


def test_correlates_queue_agent_legs():
    customer = make_event(
        "customer-1",
        call_direction="inbound",
        channel_call_uuid="customer-1",
    )

    agent_one = make_event(
        "agent-1",
        call_direction="outbound",
        cc_member_session_uuid="customer-1",
    )

    agent_two = make_event(
        "agent-2",
        call_direction="outbound",
        cc_member_session_uuid="customer-1",
    )

    correlator = CallCorrelator(
        [
            customer,
            agent_one,
            agent_two,
        ]
    )

    assert correlator.correlate("customer-1") == {
        "customer-1",
        "agent-1",
        "agent-2",
    }


def test_finds_inbound_root():
    customer = make_event(
        "customer-1",
        call_direction="inbound",
        channel_call_uuid="customer-1",
    )

    agent = make_event(
        "agent-1",
        call_direction="outbound",
        channel_call_uuid="customer-1",
        other_leg_unique_id="customer-1",
    )

    correlator = CallCorrelator([agent, customer])

    assert correlator.find_root_uuid("agent-1") == "customer-1"


def test_ivr_transfer_keeps_same_uuid():
    uuid = "customer-ivr-1"

    create = make_event(
        uuid,
        event_name="CHANNEL_CREATE",
        call_direction="inbound",
        channel_call_uuid=uuid,
    )

    ivr_enter = make_event(
        uuid,
        event_name="CUSTOM",
        event_subclass="menu::enter",
    )

    ivr_exit = make_event(
        uuid,
        event_name="CUSTOM",
        event_subclass="menu::exit",
    )

    correlator = CallCorrelator(
        [
            create,
            ivr_enter,
            ivr_exit,
        ]
    )

    assert correlator.correlate(uuid) == {uuid}
    assert correlator.find_root_uuid(uuid) == uuid
