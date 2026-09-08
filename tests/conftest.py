from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from adaptive_trip.domain.models import Candidate, ChangeEvent, Observation, TripState


@dataclass(frozen=True)
class Scenario:
    state: TripState
    event: ChangeEvent
    observations: list[Observation]
    candidates: list[Candidate]
    now: datetime
    oracle: dict[str, object]


@pytest.fixture
def scenario():
    def load(name: str) -> Scenario:
        fixture = Path(__file__).parent / "fixtures" / f"{name}.json"
        raw = json.loads(fixture.read_text(encoding="utf-8"))
        return Scenario(
            state=TripState.model_validate(raw["state"]),
            event=ChangeEvent.model_validate(raw["event"]),
            observations=[Observation.model_validate(value) for value in raw["observations"]],
            candidates=[Candidate.model_validate(value) for value in raw["candidates"]],
            now=datetime.fromisoformat(raw["now"]),
            oracle=raw["oracle"],
        )

    return load
