from __future__ import annotations

from datetime import timedelta

import pytest

from adaptive_trip.domain.models import Candidate, Proposal, Report


def _proposal(state, now) -> Proposal:
    return Proposal(
        id="proposal-1",
        trip_id=state.id,
        base_version=state.version,
        created_at=now,
        expires_at=now + timedelta(minutes=10),
        candidates=[
            Candidate(
                id="keep-plan",
                items=state.items,
                rationale="Keep the confirmed schedule.",
                signature="keep-plan",
            )
        ],
        reports={"keep-plan": Report(checks=[])},
        status="pending",
        reason="test",
    )


@pytest.mark.asyncio
async def test_accept_is_idempotent(tmp_path, scenario) -> None:
    from adaptive_trip.services.decisions import DecisionService
    from adaptive_trip.storage.repository import Repository

    loaded = scenario("rain")
    repository = Repository(tmp_path / "trip.db")
    repository.create(loaded.state)
    repository.save_proposal(_proposal(loaded.state, loaded.now))
    service = DecisionService(repository, clock=lambda: loaded.now)

    first = await service.decide(
        loaded.state.id, "proposal-1", "keep-plan", "accept", "choice-1"
    )
    again = await service.decide(
        loaded.state.id, "proposal-1", "keep-plan", "accept", "choice-1"
    )

    assert first.status == "applied"
    assert again.state.version == first.state.version


@pytest.mark.asyncio
async def test_reject_preserves_the_confirmed_itinerary(tmp_path, scenario) -> None:
    from adaptive_trip.services.decisions import DecisionService
    from adaptive_trip.storage.repository import Repository

    loaded = scenario("rain")
    repository = Repository(tmp_path / "trip.db")
    repository.create(loaded.state)
    repository.save_proposal(_proposal(loaded.state, loaded.now))
    service = DecisionService(repository, clock=lambda: loaded.now)

    result = await service.decide(
        loaded.state.id, "proposal-1", None, "reject", "choice-2"
    )

    assert result.status == "rejected"
    assert repository.get(loaded.state.id).model_dump_json() == loaded.state.model_dump_json()
