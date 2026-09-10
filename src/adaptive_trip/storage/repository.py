from __future__ import annotations

import sqlite3
from datetime import datetime
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

    def save_draft(self, draft_id: str, draft_json: str, preferences_json: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO drafts (id, draft_json, preferences_json)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    draft_json = excluded.draft_json,
                    preferences_json = excluded.preferences_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (draft_id, draft_json, preferences_json),
            )

    def get_draft(self, draft_id: str) -> tuple[str, str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT draft_json, preferences_json FROM drafts WHERE id = ?",
                (draft_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"draft {draft_id!r} does not exist")
        return row["draft_json"], row["preferences_json"]

    def get_draft_confirmation(self, draft_id: str, request_id: str) -> TripState:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT trips.state_json
                FROM draft_confirmation_requests
                JOIN trips ON trips.id = draft_confirmation_requests.trip_id
                WHERE draft_confirmation_requests.draft_id = ?
                  AND draft_confirmation_requests.request_id = ?
                """,
                (draft_id, request_id),
            ).fetchone()
        if row is None:
            raise KeyError("draft confirmation does not exist")
        return TripState.model_validate_json(row["state_json"])

    def confirm_draft(
        self,
        *,
        draft_id: str,
        request_id: str,
        draft_json: str,
        state: TripState,
    ) -> TripState:
        with self._transaction() as connection:
            existing = connection.execute(
                """
                SELECT trips.state_json
                FROM draft_confirmation_requests
                JOIN trips ON trips.id = draft_confirmation_requests.trip_id
                WHERE draft_confirmation_requests.draft_id = ?
                  AND draft_confirmation_requests.request_id = ?
                """,
                (draft_id, request_id),
            ).fetchone()
            if existing is not None:
                return TripState.model_validate_json(existing["state_json"])
            connection.execute(
                "INSERT INTO trips (id, version, state_json) VALUES (?, ?, ?)",
                (state.id, state.version, state.model_dump_json()),
            )
            connection.execute(
                """
                INSERT INTO draft_confirmation_requests (draft_id, request_id, trip_id)
                VALUES (?, ?, ?)
                """,
                (draft_id, request_id, state.id),
            )
            connection.execute(
                "UPDATE drafts SET draft_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (draft_json, draft_id),
            )
            return state

    def get(self, trip_id: str) -> TripState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM trips WHERE id = ?", (trip_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"trip {trip_id!r} does not exist")
        return TripState.model_validate_json(row["state_json"])

    def active_trips(self) -> list[TripState]:
        with self._connect() as connection:
            rows = connection.execute("SELECT state_json FROM trips").fetchall()
        return [
            state
            for row in rows
            if (state := TripState.model_validate_json(row["state_json"])).travel_mode
        ]

    def active_due_trips(self, now: datetime) -> list[TripState]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT trips.state_json, monitor_schedule.next_check_at
                FROM trips
                LEFT JOIN monitor_schedule ON monitor_schedule.trip_id = trips.id
                """
            ).fetchall()
        due: list[TripState] = []
        for row in rows:
            state = TripState.model_validate_json(row["state_json"])
            next_check_at = row["next_check_at"]
            if state.travel_mode and (
                next_check_at is None or datetime.fromisoformat(next_check_at) <= now
            ):
                due.append(state)
        return due

    def update_next_check(self, trip_id: str, at: datetime) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO monitor_schedule (trip_id, next_check_at)
                VALUES (?, ?)
                ON CONFLICT(trip_id) DO UPDATE SET next_check_at = excluded.next_check_at
                """,
                (trip_id, at.isoformat()),
            )

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

    def events(self, trip_id: str) -> list[ChangeEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM events WHERE trip_id = ? ORDER BY created_at, id",
                (trip_id,),
            ).fetchall()
        return [ChangeEvent.model_validate_json(row["event_json"]) for row in rows]

    def apply_event(self, state: TripState, event: ChangeEvent, *, expected_version: int) -> tuple[TripState, bool]:
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT event_json FROM events WHERE trip_id = ? AND fingerprint = ?",
                (event.trip_id, event.fingerprint),
            ).fetchone()
            if existing is not None:
                return state, False
            cursor = connection.execute(
                """
                UPDATE trips SET version = ?, state_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND version = ?
                """,
                (state.version, state.model_dump_json(), state.id, expected_version),
            )
            if cursor.rowcount != 1:
                raise ValueError("trip version conflict")
            connection.execute(
                "INSERT INTO events (id, trip_id, fingerprint, event_json) VALUES (?, ?, ?, ?)",
                (event.id, event.trip_id, event.fingerprint, event.model_dump_json()),
            )
            return state, True

    def event_exists(self, trip_id: str, fingerprint: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM events WHERE trip_id = ? AND fingerprint = ?",
                (trip_id, fingerprint),
            ).fetchone()
        return row is not None

    def create_run(self, run_id: str, trip_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs (id, trip_id, status) VALUES (?, ?, 'pending')",
                (run_id, trip_id),
            )

    def update_run(self, run_id: str, *, status: str, proposal_id: str | None = None, error: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, proposal_id = ?, error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, proposal_id, error, run_id),
            )

    def get_run(self, run_id: str) -> dict[str, str | None]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, trip_id, status, proposal_id, error FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"run {run_id!r} does not exist")
        return dict(row)

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

    def pending_proposals(self, trip_id: str) -> list[Proposal]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT proposal_json FROM proposals WHERE trip_id = ? ORDER BY created_at", (trip_id,)
            ).fetchall()
        return [
            proposal
            for row in rows
            if (proposal := Proposal.model_validate_json(row["proposal_json"])).status == "pending"
        ]

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
