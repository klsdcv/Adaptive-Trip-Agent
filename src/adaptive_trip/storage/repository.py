from __future__ import annotations

import sqlite3
from pathlib import Path

from adaptive_trip.domain.models import ChangeEvent, TripState


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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _transaction(self):
        connection = self._connect()
        connection.execute("BEGIN IMMEDIATE")
        return connection
