import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.call_history import CallHistory


class HistoryStore:
    def __init__(self, db_path: str | Path = "call_history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS call_histories (
                    call_id TEXT PRIMARY KEY,
                    started_at TEXT,
                    ended_at TEXT,
                    tenant TEXT,
                    customer_number TEXT,
                    did TEXT,
                    direction TEXT,
                    answered INTEGER NOT NULL DEFAULT 0,
                    hangup_cause TEXT,
                    talk_time REAL,
                    queues TEXT NOT NULL DEFAULT '[]',
                    agents TEXT NOT NULL DEFAULT '[]',
                    history_json TEXT NOT NULL
                )
                """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_customer
                ON call_histories(customer_number)
                """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_tenant
                ON call_histories(tenant)
                """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_started
                ON call_histories(started_at)
                """)

    @staticmethod
    def _value(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _extract_values(
        history: CallHistory,
    ) -> tuple[list[str], list[str]]:
        queues: set[str] = set()
        agents: set[str] = set()

        for leg in history.legs:
            if leg.role == "agent" and leg.destination:
                agents.add(leg.destination)

        for step in history.timeline:
            queue = step.detail.get("queue")
            agent = step.detail.get("agent")

            if queue:
                queues.add(str(queue))

            if agent:
                agents.add(str(agent))

        return sorted(queues), sorted(agents)

    def save(self, history: CallHistory) -> None:
        queues, agents = self._extract_values(history)

        payload = history.model_dump(mode="json")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO call_histories (
                    call_id,
                    started_at,
                    ended_at,
                    tenant,
                    customer_number,
                    did,
                    direction,
                    answered,
                    hangup_cause,
                    talk_time,
                    queues,
                    agents,
                    history_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT(call_id) DO UPDATE SET
                    started_at = excluded.started_at,
                    ended_at = excluded.ended_at,
                    tenant = excluded.tenant,
                    customer_number = excluded.customer_number,
                    did = excluded.did,
                    direction = excluded.direction,
                    answered = excluded.answered,
                    hangup_cause = excluded.hangup_cause,
                    talk_time = excluded.talk_time,
                    queues = excluded.queues,
                    agents = excluded.agents,
                    history_json = excluded.history_json
                """,
                (
                    history.call_id,
                    self._value(history.started_at),
                    self._value(history.ended_at),
                    history.tenant,
                    history.customer_number,
                    history.did,
                    history.direction,
                    int(history.answered),
                    history.hangup_cause,
                    history.durations_sec.talk,
                    json.dumps(queues),
                    json.dumps(agents),
                    json.dumps(payload),
                ),
            )

    def get(self, call_id: str) -> CallHistory | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT history_json
                FROM call_histories
                WHERE call_id = ?
                """,
                (call_id,),
            ).fetchone()

        if row is None:
            return None

        return CallHistory.model_validate(json.loads(row["history_json"]))

    def search(
        self,
        number: str | None = None,
        did: str | None = None,
        tenant: str | None = None,
        queue: str | None = None,
        agent: str | None = None,
        hangup_cause: str | None = None,
        answered: bool | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        min_talk_time: float | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[int, list[CallHistory]]:
        clauses: list[str] = []
        params: list[Any] = []

        if number:
            clauses.append("customer_number = ?")
            params.append(number)

        if did:
            clauses.append("did = ?")
            params.append(did)

        if tenant:
            clauses.append("tenant = ?")
            params.append(tenant)

        if hangup_cause:
            clauses.append("hangup_cause = ?")
            params.append(hangup_cause)

        if answered is not None:
            clauses.append("answered = ?")
            params.append(int(answered))

        if date_from:
            clauses.append("started_at >= ?")
            params.append(date_from.isoformat())

        if date_to:
            clauses.append("started_at <= ?")
            params.append(date_to.isoformat())

        if min_talk_time is not None:
            clauses.append("COALESCE(talk_time, 0) >= ?")
            params.append(min_talk_time)

        if queue:
            clauses.append("queues LIKE ?")
            params.append(f'%"{queue}"%')

        if agent:
            clauses.append("agents LIKE ?")
            params.append(f'%"{agent}"%')

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._connect() as connection:
            total = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM call_histories
                {where}
                """,
                params,
            ).fetchone()[0]

            rows = connection.execute(
                f"""
                SELECT history_json
                FROM call_histories
                {where}
                ORDER BY started_at ASC, call_id ASC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        histories = [
            CallHistory.model_validate(json.loads(row["history_json"])) for row in rows
        ]

        return total, histories
