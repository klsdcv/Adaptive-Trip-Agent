from __future__ import annotations

from datetime import timedelta

import pytest

from adaptive_trip.domain.models import Candidate, Item, Observation, PlacesData, RouteData


def _indoor_candidate(loaded, place_id: str, title: str) -> Candidate:
    park = loaded.state.items[1]
    replacement = Item(
        id=park.id,
        place_id=place_id,
        title=title,
        activity_type="indoor",
        start=park.start,
        end=park.end,
        status=park.status,
        fixed=False,
        rain_sensitive=False,
    )
    return Candidate(
        id=f"{place_id}-plan",
        items=[loaded.state.items[0], replacement, loaded.state.items[2]],
        rationale=f"Use {title} instead of the rain-sensitive outdoor stop.",
        signature=f"{place_id}|indoor",
    )


def _confirmed_observations(loaded, candidates: list[Candidate]) -> list[Observation]:
    observations: list[Observation] = []
    dinner = loaded.state.items[2]
    for candidate in candidates:
        replacement = candidate.items[1]
        observations.extend(
            [
                Observation(
                    id=f"opening-{replacement.place_id}",
                    kind="place",
                    status="ok",
                    observed_at=loaded.now,
                    valid_until=loaded.now + timedelta(hours=4),
                    source="synthetic",
                    data=PlacesData(
                        place_id=replacement.place_id,
                        opening_intervals=[(replacement.start, replacement.end + timedelta(hours=1))],
                    ),
                ),
                Observation(
                    id=f"route-{replacement.place_id}",
                    kind="route",
                    status="ok",
                    observed_at=loaded.now,
                    valid_until=loaded.now + timedelta(hours=4),
                    source="synthetic",
                    data=RouteData(
                        origin_place_id=replacement.place_id,
                        destination_place_id=dinner.place_id,
                        departure_at=replacement.end,
                        duration_seconds=900,
                    ),
                ),
                Observation(
                    id="opening-dinner",
                    kind="place",
                    status="ok",
                    observed_at=loaded.now,
                    valid_until=loaded.now + timedelta(hours=6),
                    source="synthetic",
                    data=PlacesData(
                        place_id=dinner.place_id,
                        opening_intervals=[(dinner.start, dinner.end)],
                    ),
                ),
            ]
        )
    return observations


@pytest.mark.asyncio
async def test_replan_keeps_original_and_offers_three_valid_alternatives(scenario) -> None:
    from adaptive_trip.agent.contracts import AgentAction
    from adaptive_trip.agent.gateway import ScriptedGateway
    from adaptive_trip.agent.graph import Replanner
    from adaptive_trip.tools.synthetic import SyntheticTools

    loaded = scenario("rain")
    candidates = [
        _indoor_candidate(loaded, "synthetic:museum", "Museum"),
        _indoor_candidate(loaded, "synthetic:market", "Market"),
        _indoor_candidate(loaded, "synthetic:cafe", "Cafe"),
    ]
    observations = _confirmed_observations(loaded, candidates)
    original = loaded.state.model_dump_json()
    replanner = Replanner(
        ScriptedGateway([AgentAction(kind="candidates", candidates=candidates, reason="Rain fallback")]),
        SyntheticTools(observations),
    )

    result = await replanner.run(loaded.state, loaded.event, observations, loaded.now)

    assert result.proposal is not None
    assert len(result.proposal.candidates) == 3
    assert all(report.eligible for report in result.proposal.reports.values())
    assert loaded.state.model_dump_json() == original
