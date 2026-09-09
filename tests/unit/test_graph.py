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


@pytest.mark.asyncio
async def test_replanner_executes_requested_tool_and_returns_evidence_to_model(scenario) -> None:
    from adaptive_trip.agent.contracts import AgentAction
    from adaptive_trip.agent.graph import Replanner
    from adaptive_trip.tools.contracts import ToolRequest
    from adaptive_trip.tools.synthetic import SyntheticTools

    loaded = scenario("rain")
    observation = Observation(
        id="details-museum",
        kind="place",
        status="ok",
        observed_at=loaded.now,
        valid_until=loaded.now + timedelta(hours=1),
        source="synthetic",
        data=PlacesData(
            place_id="synthetic:museum",
            opening_intervals=[
                (loaded.state.items[1].start, loaded.state.items[1].end)
            ],
        ),
    )

    class RecordingGateway:
        def __init__(self) -> None:
            self.contexts: list[dict[str, object]] = []
            self.actions = iter(
                [
                    AgentAction(
                        kind="tool",
                        request=ToolRequest(
                            name="place_details",
                            arguments={"place_id": "synthetic:museum"},
                            sku="places_details",
                            units=1,
                        ),
                        reason="Confirm opening hours.",
                    ),
                    AgentAction(kind="stop", reason="Evidence collected."),
                ]
            )

        async def next(self, context: dict[str, object]) -> AgentAction:
            self.contexts.append(context)
            return next(self.actions)

    gateway = RecordingGateway()
    result = await Replanner(gateway, SyntheticTools([observation])).run(
        loaded.state, loaded.event, [], loaded.now
    )

    assert result.model_calls == 2
    assert result.tool_calls == 1
    assert [item.id for item in result.observations] == ["details-museum"]
    assert gateway.contexts[1]["observations"][0]["id"] == "details-museum"


@pytest.mark.asyncio
async def test_replanner_returns_validation_failures_for_candidate_revision(scenario) -> None:
    from adaptive_trip.agent.contracts import AgentAction
    from adaptive_trip.agent.graph import Replanner
    from adaptive_trip.tools.synthetic import SyntheticTools

    loaded = scenario("rain")
    valid_candidates = [
        _indoor_candidate(loaded, "synthetic:museum", "Museum"),
        _indoor_candidate(loaded, "synthetic:market", "Market"),
        _indoor_candidate(loaded, "synthetic:cafe", "Cafe"),
    ]
    observations = _confirmed_observations(loaded, valid_candidates)
    fixed_dinner = loaded.state.items[2]
    broken_dinner = fixed_dinner.model_copy(
        update={"start": fixed_dinner.start + timedelta(minutes=30)}
    )
    invalid_candidate = Candidate(
        id="moves-fixed-dinner",
        items=[*loaded.state.items[:2], broken_dinner],
        rationale="Invalid first attempt.",
        signature="moves-fixed-dinner",
    )

    class RevisingGateway:
        def __init__(self) -> None:
            self.contexts: list[dict[str, object]] = []
            self.actions = iter([
                AgentAction(
                    kind="candidates",
                    candidates=[invalid_candidate],
                    reason="First attempt.",
                ),
                AgentAction(
                    kind="candidates",
                    candidates=valid_candidates,
                    reason="Revised after deterministic validation.",
                ),
            ])

        async def next(self, context: dict[str, object]) -> AgentAction:
            self.contexts.append(context)
            return next(self.actions)

    gateway = RevisingGateway()
    result = await Replanner(gateway, SyntheticTools(observations)).run(
        loaded.state, loaded.event, observations, loaded.now
    )

    assert len(result.proposal.candidates) == 3
    assert result.model_calls == 2
    assert any(
        check["code"] == "fixed_time" and check["status"] == "fail"
        for check in gateway.contexts[1]["validation"]
    )


@pytest.mark.asyncio
async def test_candidate_validation_uses_observation_created_by_tool_call(scenario) -> None:
    from adaptive_trip.agent.contracts import AgentAction
    from adaptive_trip.agent.gateway import ScriptedGateway
    from adaptive_trip.agent.graph import Replanner
    from adaptive_trip.domain.models import Constraints
    from adaptive_trip.tools.contracts import ToolRequest
    from adaptive_trip.tools.synthetic import SyntheticTools

    loaded = scenario("rain")
    original = loaded.state.items[1]
    replacement = original.model_copy(
        update={
            "place_id": "synthetic:museum",
            "title": "Museum",
            "activity_type": "indoor",
            "rain_sensitive": False,
        }
    )
    state = loaded.state.model_copy(
        update={"items": [original], "constraints": Constraints()}
    )
    candidate = Candidate(
        id="museum-plan",
        items=[replacement],
        rationale="Move indoors.",
        signature="synthetic:museum|indoor",
    )
    details = Observation(
        id="details-museum",
        kind="place",
        status="ok",
        observed_at=loaded.now,
        valid_until=loaded.now + timedelta(hours=1),
        source="synthetic",
        data=PlacesData(
            place_id="synthetic:museum",
            opening_intervals=[(replacement.start, replacement.end)],
        ),
    )
    gateway = ScriptedGateway([
        AgentAction(
            kind="tool",
            request=ToolRequest(
                name="place_details",
                arguments={"place_id": "synthetic:museum"},
                sku="places_details",
                units=1,
            ),
            reason="Check the museum.",
        ),
        AgentAction(kind="candidates", candidates=[candidate], reason="Verified."),
    ])

    result = await Replanner(
        gateway, SyntheticTools([details]), target_candidates=1
    ).run(state, loaded.event, [], loaded.now)

    assert [item.id for item in result.proposal.candidates] == ["museum-plan"]


@pytest.mark.asyncio
async def test_replanner_retries_invalid_model_shape_within_call_limit(scenario) -> None:
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
    gateway = ScriptedGateway([
        AgentAction(kind="stop", reason="invalid_model_response"),
        AgentAction(
            kind="candidates",
            candidates=candidates,
            reason="Valid retry.",
        ),
    ])

    result = await Replanner(gateway, SyntheticTools(observations)).run(
        loaded.state, loaded.event, observations, loaded.now
    )

    assert result.model_calls == 2
    assert len(result.proposal.candidates) == 3
