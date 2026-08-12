import json
from collections.abc import Callable

from kafka import KafkaConsumer


class CallKafkaConsumer:
    def __init__(
        self,
        brokers: list[str],
        topic: str,
        group_id: str,
        on_event: Callable[[str], None],
    ):
        self.brokers = brokers
        self.topic = topic
        self.group_id = group_id
        self.on_event = on_event

    def consume(self) -> None:
        consumer = KafkaConsumer(
            self.topic,
            bootstrap_servers=self.brokers,
            group_id=self.group_id,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )

        try:
            for message in consumer:
                line = self._to_event_line(message.value)
                if line is None:
                    continue

                self.on_event(line)
        finally:
            consumer.close()

    @staticmethod
    def _to_event_line(value: object) -> str | None:
        if not isinstance(value, dict):
            return None

        timestamp = value.get("timestamp")
        data = value.get("data")

        if not timestamp or not isinstance(data, dict):
            return None

        return f"{timestamp}#:EVENT['freeswitch']:" f"{data}"
