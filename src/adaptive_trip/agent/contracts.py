from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from adaptive_trip.domain.models import Candidate


class AgentAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["candidates", "stop"]
    candidates: list[Candidate] = Field(default_factory=list)
    reason: str


class ModelGateway(Protocol):
    async def next(self, context: dict[str, object]) -> AgentAction:
        """Return a schema-validated action; this method never performs a tool call."""
