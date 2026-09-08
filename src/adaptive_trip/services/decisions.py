from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from adaptive_trip.domain.models import DecisionResult
from adaptive_trip.storage.repository import Repository


class DecisionService:
    def __init__(self, repository: Repository, *, clock: Callable[[], datetime]) -> None:
        self._repository = repository
        self._clock = clock

    async def decide(
        self,
        trip_id: str,
        proposal_id: str,
        candidate_id: str | None,
        action: Literal["accept", "reject"],
        request_id: str,
    ) -> DecisionResult:
        return self._repository.apply_decision(
            trip_id=trip_id,
            proposal_id=proposal_id,
            candidate_id=candidate_id,
            action=action,
            request_id=request_id,
            now=self._clock(),
        )
