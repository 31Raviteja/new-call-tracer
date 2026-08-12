from abc import ABC, abstractmethod
from collections.abc import Iterator


class EventSource(ABC):
    """Base interface for event-producing sources."""

    @abstractmethod
    def events(self) -> Iterator[str]:
        """Yield raw FreeSWITCH event lines."""
        raise NotImplementedError
