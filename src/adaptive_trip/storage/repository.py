from __future__ import annotations

import sqlite3
from pathlib import Path

from adaptive_trip.domain.models import (
    ChangeEvent,
    DecisionResult,
    Proposal,
    TripState,
)


class Repository:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
            )

    def create(self, state: TripState) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO trips (id, version, state_json) VALUES (?, ?, ?)",
                (state.id, state.version, state.model_dump_json()),
            )

    def get(self, trip_id: str) -> TripState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM trips WHERE id = ?", (trip_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"trip {trip_id!r} does not exist")
        return TripState.model_validate_json(row["state_json"])

    def compare_and_swap(self, state: TripState, *, expected_version: int) -> bool:
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE trips
                SET version = ?, state_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND version = ?
                """,
                (state.version, state.model_dump_json(), state.id, expected_version),
            )
            return cursor.rowcount == 1

    def save_event(self, event: ChangeEvent) -> bool:
        with self._transaction() as connection:
            try:
                connection.execute(
                    "INSERT INTO events (id, trip_id, fingerprint, event_json) VALUES (?, ?, ?, ?)",
                    (event.id, event.trip_id, event.fingerprint, event.model_dump_json()),
                )
            except sqlite3.IntegrityError:
                return False
            return True

    def save_proposal(self, proposal: Proposal) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO proposals (id, trip_id, proposal_json) VALUES (?, ?, ?)",
                (proposal.id, proposal.trip_id, proposal.model_dump_json()),
            )

    def get_proposal(self, proposal_id: str) -> Proposal:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT proposal_json FROM proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"proposal {proposal_id!r} does not exist")
        return Proposal.model_validate_json(row["proposal_json"])

    def apply_decision(
        self,
        *,
        trip_id: str,
        proposal_id: str,
        candidate_id: str | None,
        action: str,
        request_id: str,
        now,
    ) -> DecisionResult:
        with self._transaction() as connection:
            stored = connection.execute(
                "SELECT result_json FROM decision_requests WHERE trip_id = ? AND request_id = ?",
                (trip_id, request_id),
            ).fetchone()
            if stored is not None:
                return DecisionResult.model_validate_json(stored["result_json"])

            state_row = connection.execute(
                "SELECT state_json FROM trips WHERE id = ?", (trip_id,)
            ).fetchone()
            proposal_row = connection.execute(
                "SELECT proposal_json FROM proposals WHERE id = ? AND trip_id = ?",
                (proposal_id, trip_id),
            ).fetchone()
            if state_row is None or proposal_row is None:
                state = TripState.model_validate_json(state_row["state_json"]) if state_row else TripState(id="invalid", version=0, timezone="UTC", items=[], now=now)
                result = DecisionResult(status="invalid", state=state, proposal_id=proposal_id)
                self._store_decision(connection, trip_id, request_id, result)
                return result

            state = TripState.model_validate_json(state_row["state_json"])
            proposal = Proposal.model_validate_json(proposal_row["proposal_json"])
            if proposal.base_version != state.version or proposal.expires_at <= now:
                result = DecisionResult(status="stale", state=state, proposal_id=proposal_id)
            elif action == "reject":
                result = DecisionResult(status="rejected", state=state, proposal_id=proposal_id)
            elif action == "accept":
                candidate = next((item for item in proposal.candidates if item.id == candidate_id), None)
                report = proposal.reports.get(candidate_id or "")
                if candidate is None or report is None:
                    result = DecisionResult(status="invalid", state=state, proposal_id=proposal_id)
                elif not report.eligible:
                    result = DecisionResult(status="needs_confirmation", state=state, proposal_id=proposal_id)
                else:
                    updated = state.model_copy(update={"items": candidate.items, "version": state.version + 1})
                    connection.execute(
                        "UPDATE trips SET version = ?, state_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND version = ?",
                        (updated.version, updated.model_dump_json(), trip_id, state.version),
                    )
                    result = DecisionResult(status="applied", state=updated, proposal_id=proposal_id)
            else:
                result = DecisionResult(status="invalid", state=state, proposal_id=proposal_id)

            self._store_decision(connection, trip_id, request_id, result)
            return result

    @staticmethod
    def _store_decision(connection: sqlite3.Connection, trip_id: str, request_id: str, result: DecisionResult) -> None:
        connection.execute(
            "INSERT INTO decision_requests (trip_id, request_id, result_json) VALUES (?, ?, ?)",
            (trip_id, request_id, result.model_dump_json()),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _transaction(self):
        connection = self._connect()
        connection.execute("BEGIN IMMEDIATE")
        return connection
