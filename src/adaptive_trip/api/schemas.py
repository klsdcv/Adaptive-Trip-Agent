from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from adaptive_trip.domain.models import ChangeEvent, Observation


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    candidate_id: str | None = None
    action: Literal["accept", "reject"]
    request_id: str


class ReplanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: ChangeEvent
    observations: list[Observation]


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "weather", "delay", "closed", "completion", "fatigue", "fixed",
        "preference", "position", "expense",
    ]
    payload: dict[str, object] = Field(default_factory=dict)
    expected_version: int = Field(ge=0)
    request_id: str = Field(min_length=1)


class ModeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    expected_version: int = Field(ge=0)
    request_id: str = Field(min_length=1)


class RunStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    trip_id: str
    status: Literal["pending", "completed", "failed"]
    proposal_id: str | None = None
    error: str | None = None


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    preferences: dict[str, object] = Field(default_factory=dict)


class DraftConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed_fields: dict[str, object]
    request_id: str = Field(min_length=1)
