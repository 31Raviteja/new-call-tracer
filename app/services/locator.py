from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path


class CallLocator(ABC):
    """Locate log sources relevant to a customer number."""

    @abstractmethod
    def locate(self, number: str) -> Sequence[str | Path]:
        """Return log files or log regions relevant to the number."""
        raise NotImplementedError
