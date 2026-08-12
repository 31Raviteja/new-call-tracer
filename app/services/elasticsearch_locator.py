from collections.abc import Sequence

from app.services.locator import CallLocator


class ElasticsearchLocator(CallLocator):
    """Locate call-related log files using Elasticsearch."""

    def __init__(
        self,
        client,
        index_name: str,
    ):
        self.client = client
        self.index_name = index_name

    def locate(self, number: str) -> Sequence[str]:
        response = self.client.search(
            index=self.index_name,
            query={
                "multi_match": {
                    "query": number,
                    "fields": [
                        "caller_number",
                        "destination_number",
                        "message",
                    ],
                }
            },
        )

        locations: list[str] = []

        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})

            location = (
                source.get("log_file")
                or source.get("log_path")
                or source.get("file")
                or source.get("path")
            )

            if location:
                locations.append(str(location))

        return locations
