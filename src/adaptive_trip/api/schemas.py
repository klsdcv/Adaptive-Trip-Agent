from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    candidate_id: str | None = None
    action: Literal["accept", "reject"]
    request_id: str
