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


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    preferences: dict[str, object] = Field(default_factory=dict)
