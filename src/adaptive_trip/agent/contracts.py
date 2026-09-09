from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptive_trip.domain.models import Candidate
from adaptive_trip.tools.contracts import ToolRequest


class AgentAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["tool", "candidates", "stop"]
    request: ToolRequest | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    reason: str
    provider_response_id: str | None = None
    provider_call_id: str | None = None

    @model_validator(mode="after")
    def tool_action_requires_request(self) -> AgentAction:
        if self.kind == "tool" and self.request is None:
            raise ValueError("tool action requires a request")
        if self.kind != "tool" and self.request is not None:
            raise ValueError("only tool actions may include a request")
        return self


class ModelGateway(Protocol):
    async def next(self, context: dict[str, object]) -> AgentAction:
        """Return a schema-validated action; this method never performs a tool call."""
