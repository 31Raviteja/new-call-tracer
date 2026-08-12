from collections.abc import Sequence
from pathlib import Path

from app.services.locator import CallLocator


class FolderLocator(CallLocator):
    """Locate log files in the configured folder."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir

    def locate(self, number: str) -> Sequence[Path]:
        if not self.log_dir.exists() or not self.log_dir.is_dir():
            return []

        return [
            path
            for path in sorted(
                [
                    *self.log_dir.glob("*.log"),
                    *self.log_dir.glob("*.txt"),
                ]
            )
            if path.is_file()
        ]
