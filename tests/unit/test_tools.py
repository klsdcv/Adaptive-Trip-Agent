from __future__ import annotations

import pytest

from adaptive_trip.domain.models import Observation, RouteData


@pytest.mark.asyncio
async def test_synthetic_tools_return_matching_route_observation() -> None:
    from adaptive_trip.tools.contracts import ToolRequest
    from adaptive_trip.tools.synthetic import SyntheticTools

    observation = Observation(
        id="route-1",
        kind="route",
        status="ok",
        observed_at="2026-09-08T14:30:00+09:00",
        valid_until="2026-09-08T18:00:00+09:00",
        source="synthetic",
        data=RouteData(
            origin_place_id="synthetic:park",
            destination_place_id="synthetic:dinner",
            departure_at="2026-09-08T17:00:00+09:00",
            duration_seconds=900,
        ),
    )
    tools = SyntheticTools([observation])

    result = await tools.call(
        ToolRequest(
            name="route",
            arguments={
                "origin_place_id": "synthetic:park",
                "destination_place_id": "synthetic:dinner",
            },
            sku="routes_essentials",
            units=1,
        )
    )

    assert result.observation == observation
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_synthetic_tools_report_missing_for_an_unprepared_request() -> None:
    from adaptive_trip.tools.contracts import ToolRequest
    from adaptive_trip.tools.synthetic import SyntheticTools

    result = await SyntheticTools([]).call(
        ToolRequest(
            name="weather",
            arguments={"latitude": 34.7, "longitude": 135.5},
            sku="weather",
            units=1,
        )
    )

    assert result.observation.status == "missing"
