import sqlite3
from pathlib import Path

from app.config import settings
from app.models.events import ParsedEvent
from app.services.normalizer import EventNormalizer
from app.services.parser import EventParser


class LogSearchIndex:
    def __init__(
        self,
        db_path: str | Path = "call_trace_index.db",
        log_dir: str | Path | None = None,
    ):
        self.db_path = Path(db_path)

        self.log_dir = (
            Path(log_dir)
            if log_dir is not None
            else Path(settings.log_dir)
        )

    def _connect(self):
        connection = sqlite3.connect(
            self.db_path,
            timeout=60,
        )

        connection.row_factory = sqlite3.Row

        return connection

    def exists(self) -> bool:
        return self.db_path.exists()

    def stats(self) -> dict[str, str]:
        if not self.db_path.exists():
            return {}

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT key, value
                FROM metadata
                """
            ).fetchall()

        return {
            row["key"]: row["value"]
            for row in rows
        }

    # ============================================================
    # DATABASE CREATION
    # ============================================================

    def _create_database(self):
        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:

            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;

                DROP TABLE IF EXISTS metadata;
                DROP TABLE IF EXISTS events;
                DROP TABLE IF EXISTS numbers;
                DROP TABLE IF EXISTS relationships;

                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    byte_offset INTEGER NOT NULL,
                    byte_length INTEGER NOT NULL
                );

                CREATE TABLE numbers (
                    number TEXT NOT NULL,
                    uuid TEXT NOT NULL
                );

                CREATE TABLE relationships (
                    uuid TEXT NOT NULL,
                    related_uuid TEXT NOT NULL
                );

                CREATE INDEX idx_events_uuid
                    ON events(uuid);

                CREATE INDEX idx_numbers_number
                    ON numbers(number);

                CREATE INDEX idx_numbers_uuid
                    ON numbers(uuid);

                CREATE INDEX idx_relationships_uuid
                    ON relationships(uuid);

                CREATE INDEX idx_relationships_related_uuid
                    ON relationships(related_uuid);
                """
            )

            connection.commit()

    # ============================================================
    # INDEX ALL LOG FILES
    # ============================================================

    def build(self):
        if not self.log_dir.exists():
            raise FileNotFoundError(
                f"Log directory does not exist: {self.log_dir}"
            )

        files = sorted(
            [
                path
                for path in self.log_dir.iterdir()
                if path.is_file()
                and path.suffix.lower() in {".log", ".txt"}
            ],
            key=lambda path: path.name,
        )

        print(
            f"Indexing {len(files)} log files..."
        )

        print(
            f"Log directory: {self.log_dir.resolve()}"
        )

        self._create_database()

        parser = EventParser()
        normalizer = EventNormalizer()

        total_events = 0
        total_numbers = 0
        total_relationships = 0

        with self._connect() as connection:

            for file_number, file_path in enumerate(
                files,
                1,
            ):
                print(
                    f"[{file_number}/{len(files)}] "
                    f"Indexing {file_path.name}..."
                )

                file_events = 0
                file_numbers = 0
                file_relationships = 0

                try:
                    with file_path.open(
                        "rb"
                    ) as file:

                        while True:
                            byte_offset = file.tell()

                            raw_line = file.readline()

                            if not raw_line:
                                break

                            byte_length = len(
                                raw_line
                            )

                            try:
                                line = raw_line.decode(
                                    "utf-8",
                                    errors="replace",
                                ).strip()

                                raw_event = parser.parse(
                                    line
                                )

                                if raw_event is None:
                                    continue

                                event = normalizer.normalize(
                                    raw_event
                                )

                                if not event.uuid:
                                    continue

                                if normalizer.is_noise(
                                    event
                                ):
                                    continue

                                # ==================================
                                # EVENTS
                                # ==================================

                                connection.execute(
                                    """
                                    INSERT INTO events (
                                        uuid,
                                        file_path,
                                        byte_offset,
                                        byte_length
                                    )
                                    VALUES (?, ?, ?, ?)
                                    """,
                                    (
                                        event.uuid,
                                        str(
                                            file_path.resolve()
                                        ),
                                        byte_offset,
                                        byte_length,
                                    ),
                                )

                                file_events += 1
                                total_events += 1

                                # ==================================
                                # NUMBERS
                                # ==================================

                                numbers = self._extract_numbers(
                                    event
                                )

                                for number in numbers:

                                    connection.execute(
                                        """
                                        INSERT INTO numbers (
                                            number,
                                            uuid
                                        )
                                        VALUES (?, ?)
                                        """,
                                        (
                                            number,
                                            event.uuid,
                                        ),
                                    )

                                    file_numbers += 1
                                    total_numbers += 1

                                # ==================================
                                # RELATIONSHIPS
                                # ==================================

                                related_uuids = (
                                    self._related_uuids(
                                        event
                                    )
                                )

                                for related_uuid in (
                                    related_uuids
                                ):

                                    if (
                                        related_uuid
                                        == event.uuid
                                    ):
                                        continue

                                    connection.execute(
                                        """
                                        INSERT INTO relationships (
                                            uuid,
                                            related_uuid
                                        )
                                        VALUES (?, ?)
                                        """,
                                        (
                                            event.uuid,
                                            related_uuid,
                                        ),
                                    )

                                    file_relationships += 1
                                    total_relationships += 1

                            except Exception:
                                # One malformed event should
                                # never stop the complete index.
                                continue

                    connection.commit()

                except OSError as exc:
                    print(
                        f"    ERROR reading "
                        f"{file_path.name}: {exc}"
                    )

                print(
                    f"    Events: {file_events:,} | "
                    f"Numbers: {file_numbers:,} | "
                    f"Relationships: "
                    f"{file_relationships:,}"
                )

            # ==============================================
            # METADATA
            # ==============================================

            metadata = {
                "log_dir": str(
                    self.log_dir.resolve()
                ),
                "files": str(
                    len(files)
                ),
                "events": str(
                    total_events
                ),
                "numbers": str(
                    total_numbers
                ),
                "relationships": str(
                    total_relationships
                ),
            }

            for key, value in metadata.items():

                connection.execute(
                    """
                    INSERT INTO metadata (
                        key,
                        value
                    )
                    VALUES (?, ?)
                    """,
                    (
                        key,
                        value,
                    ),
                )

            connection.commit()

        print()
        print("Indexing complete.")
        print(
            f"Files: {len(files)}"
        )
        print(
            f"Events: {total_events}"
        )
        print(
            f"Numbers: {total_numbers}"
        )
        print(
            f"Relationships: {total_relationships}"
        )
        print(
            f"Index: {self.db_path.resolve()}"
        )

    # ============================================================
    # NUMBER EXTRACTION
    # ============================================================

    @staticmethod
    def _extract_numbers(
        event: ParsedEvent,
    ) -> set[str]:

        values = [
            event.caller_number,
            event.destination_number,

            event.data.get(
                "Caller-Callee-ID-Number"
            ),

            event.data.get(
                "Caller-Destination-Number"
            ),

            event.data.get(
                "Caller-ANI"
            ),

            event.data.get(
                "variable_sip_req_user"
            ),

            event.data.get(
                "variable_origination_caller_id_number"
            ),

            event.data.get(
                "Other-Leg-Caller-ID-Number"
            ),

            event.data.get(
                "Other-Leg-Destination-Number"
            ),

            event.data.get(
                "Caller-Channel-Name"
            ),
        ]

        result: set[str] = set()

        for value in values:

            if value is None:
                continue

            normalized = (
                EventNormalizer._normalize_number(
                    value
                )
            )

            if normalized:
                result.add(normalized)

        return result

    # ============================================================
    # RELATIONSHIP EXTRACTION
    # ============================================================

    @staticmethod
    def _related_uuids(
        event: ParsedEvent,
    ) -> set[str]:

        candidates = (
            event.channel_call_uuid,
            event.other_leg_unique_id,
            event.originating_leg_uuid,
            event.bridge_uuid,
            event.signal_bond,
            event.cc_member_session_uuid,
            event.variable_cc_member_session_uuid,
            event.cc_member_uuid,
        )

        return {
            value
            for value in candidates
            if value
        }

    # ============================================================
    # FAST NUMBER SEARCH
    # ============================================================

    def search_uuids(
        self,
        number: str,
    ) -> set[str]:

        normalized_number = (
            EventNormalizer._normalize_number(
                number
            )
        )

        if not normalized_number:
            return set()

        if not self.db_path.exists():
            return set()

        with self._connect() as connection:

            rows = connection.execute(
                """
                SELECT DISTINCT uuid
                FROM numbers
                WHERE number = ?
                """,
                (
                    normalized_number,
                ),
            ).fetchall()

        return {
            row["uuid"]
            for row in rows
            if row["uuid"]
        }

    def count_uuids(
        self,
        number: str,
    ) -> int:
        normalized_number = (
            EventNormalizer._normalize_number(
                number
            )
        )

        if not normalized_number:
            return 0

        if not self.db_path.exists():
            return 0

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(DISTINCT uuid) AS total
                FROM numbers
                WHERE number = ?
                """,
                (normalized_number,),
            ).fetchone()

        if row is None:
            return 0

        return int(row["total"] or 0)

    # ============================================================
    # RELATIONSHIP SEARCH
    # ============================================================

    def related_uuids(
        self,
        root_uuids: set[str],
    ) -> set[str]:

        if not root_uuids:
            return set()

        if not self.db_path.exists():
            return set()

        visited = set(
            root_uuids
        )

        current = list(
            root_uuids
        )

        max_uuids = 5000

        with self._connect() as connection:

            while (
                current
                and len(visited) < max_uuids
            ):

                next_level = []

                for start in range(
                    0,
                    len(current),
                    900,
                ):

                    batch = current[
                        start:start + 900
                    ]

                    placeholders = ",".join(
                        "?"
                        for _ in batch
                    )

                    rows = connection.execute(
                        f"""
                        SELECT DISTINCT related_uuid
                        FROM relationships
                        WHERE uuid IN (
                            {placeholders}
                        )
                        """,
                        batch,
                    ).fetchall()

                    for row in rows:

                        related_uuid = row[
                            "related_uuid"
                        ]

                        if (
                            related_uuid
                            and related_uuid
                            not in visited
                        ):

                            visited.add(
                                related_uuid
                            )

                            next_level.append(
                                related_uuid
                            )

                            if (
                                len(visited)
                                >= max_uuids
                            ):
                                break

                    if (
                        len(visited)
                        >= max_uuids
                    ):
                        break

                current = next_level

        return visited

    # ============================================================
    # READ ONLY MATCHING EVENTS
    # ============================================================

    def read_events(
        self,
        uuids: set[str],
    ) -> list[ParsedEvent]:

        if not uuids:
            return []

        if not self.db_path.exists():
            return []

        uuid_list = list(
            uuids
        )

        rows = []

        with self._connect() as connection:

            for start in range(
                0,
                len(uuid_list),
                900,
            ):

                batch = uuid_list[
                    start:start + 900
                ]

                placeholders = ",".join(
                    "?"
                    for _ in batch
                )

                batch_rows = connection.execute(
                    f"""
                    SELECT
                        uuid,
                        file_path,
                        byte_offset,
                        byte_length
                    FROM events
                    WHERE uuid IN (
                        {placeholders}
                    )
                    ORDER BY
                        file_path,
                        byte_offset
                    """,
                    batch,
                ).fetchall()

                rows.extend(
                    batch_rows
                )

        if not rows:
            return []

        grouped = {}

        for row in rows:

            grouped.setdefault(
                row["file_path"],
                [],
            ).append(row)

        parser = EventParser()
        normalizer = EventNormalizer()

        events = []

        for file_path, file_rows in (
            grouped.items()
        ):

            try:

                with Path(
                    file_path
                ).open(
                    "rb"
                ) as file:

                    for row in file_rows:

                        file.seek(
                            row["byte_offset"]
                        )

                        raw_line = file.read(
                            row["byte_length"]
                        )

                        line = raw_line.decode(
                            "utf-8",
                            errors="replace",
                        ).strip()

                        raw_event = parser.parse(
                            line
                        )

                        if raw_event is None:
                            continue

                        event = normalizer.normalize(
                            raw_event
                        )

                        if normalizer.is_noise(
                            event
                        ):
                            continue

                        events.append(
                            event
                        )

            except OSError:
                continue

        return events


if __name__ == "__main__":

    index = LogSearchIndex()

    print(
        "Database:",
        index.db_path.resolve(),
    )

    print(
        "Log directory:",
        index.log_dir.resolve(),
    )

    print(
        "Exists before indexing:",
        index.exists(),
    )

    index.build()

    print()
    print(
        "Stats:",
        index.stats(),
    )