from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest


@pytest.fixture
def google_tools():
    from adaptive_trip.tools.google_places import GoogleTools

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Goog-Api-Key"] == "test-key"
        assert request.url.path == "/v1/places/synthetic:missing-hours"
        return httpx.Response(
            200,
            json={
                "id": "synthetic:missing-hours",
                "displayName": {"text": "Indoor museum"},
                "location": {"latitude": 37.5665, "longitude": 126.9780},
            },
        )

    return GoogleTools(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        api_key="test-key",
        clock=lambda: datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_missing_opening_hours_remain_unknown(google_tools) -> None:
    from adaptive_trip.tools.contracts import ToolRequest

    result = await google_tools.call(
        ToolRequest(
            name="place_details",
            arguments={"place_id": "synthetic:missing-hours"},
            sku="place_details_enterprise",
            units=1,
        )
    )

    assert result.observation.status == "ok"
    assert result.observation.data.opening_intervals is None


@pytest.mark.asyncio
async def test_route_response_is_normalized_to_duration() -> None:
    from adaptive_trip.tools.contracts import ToolRequest
    from adaptive_trip.tools.google_places import GoogleTools

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/directions/v2:computeRoutes"
        return httpx.Response(200, json={"routes": [{"duration": "420s", "distanceMeters": 650}]})

    tools = GoogleTools(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        api_key="test-key",
        clock=lambda: datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc),
    )
    result = await tools.call(ToolRequest(
        name="route",
        arguments={"origin_place_id": "ChIJ", "destination_place_id": "ChIK", "departure_at": "2026-09-08T10:00:00+09:00"},
        sku="routes", units=1,
    ))

    assert result.observation.status == "ok"
    assert result.observation.data.duration_seconds == 420


@pytest.mark.asyncio
async def test_unsupported_weather_location_is_not_counted_as_weather_data() -> None:
    from adaptive_trip.tools.contracts import ToolRequest
    from adaptive_trip.tools.google_places import GoogleTools

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/forecast/hours:lookup"
        return httpx.Response(404, json={"error": {"status": "NOT_FOUND"}})

    tools = GoogleTools(httpx.AsyncClient(transport=httpx.MockTransport(handler)), api_key="test-key")
    result = await tools.call(ToolRequest(
        name="weather", arguments={"latitude": 37.5665, "longitude": 126.9780}, sku="weather", units=1,
    ))

    assert result.observation.kind == "weather"
    assert result.observation.status == "unsupported"
    assert result.error_code == "unsupported_location"
