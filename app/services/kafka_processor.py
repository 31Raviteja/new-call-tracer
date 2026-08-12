from app.models.events import ParsedEvent
from app.services.normalizer import EventNormalizer
from app.services.parser import EventParser


class KafkaEventProcessor:
    def __init__(self):
        self.parser = EventParser()
        self.normalizer = EventNormalizer()

    def process(self, line: str) -> ParsedEvent | None:
        raw_event = self.parser.parse(line)

        if raw_event is None:
            return None

        normalized_event = self.normalizer.normalize(raw_event)

        if self.normalizer.is_noise(normalized_event):
            return None

        return normalized_event
