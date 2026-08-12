import ast
from datetime import datetime

from app.models.events import RawEvent


class EventParser:
    def __init__(self):
        self.parse_errors = 0

    def parse(self, line: str) -> RawEvent | None:
        line = line.strip()

        if "#:EVENT[" not in line:
            return None

        try:
            timestamp_text, event_text = line.split(
                "#:EVENT['freeswitch']:",
                1,
            )
        except ValueError:
            self.parse_errors += 1
            return None

        try:
            timestamp = datetime.fromisoformat(timestamp_text.strip())
        except ValueError:
            self.parse_errors += 1
            return None

        try:
            data = ast.literal_eval(event_text.strip())
        except (ValueError, SyntaxError):
            self.parse_errors += 1
            return None

        if not isinstance(data, dict):
            self.parse_errors += 1
            return None

        return RawEvent(timestamp=timestamp, data=data)
