from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from adaptive_trip.domain.models import Observation


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["places_search", "place_details", "route", "weather"]
    arguments: dict[str, Any]
    sku: str
    units: int = Field(ge=1)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation: Observation
    attempts: int = Field(ge=1)
    error_code: str | None = None


class ToolProvider(ABC):
    @abstractmethod
    async def call(self, request: ToolRequest) -> ToolResult:
        """Return a normalized observation for one bounded tool request."""
