from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest


@pytest.mark.asyncio
async def test_seoul_hourly_rain_probability_is_normalized() -> None:
    from adaptive_trip.tools.contracts import ToolRequest
    from adaptive_trip.tools.open_meteo import OpenMeteoTools

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/forecast"
        assert request.url.params["latitude"] == "37.5665"
        assert request.url.params["hourly"] == "precipitation_probability,rain,weather_code"
        return httpx.Response(200, json={
            "hourly": {
                "time": ["2026-09-08T15:00"],
                "precipitation_probability": [67],
                "rain": [1.2],
                "weather_code": [61],
            }
        })

    tools = OpenMeteoTools(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        clock=lambda: datetime(2026, 9, 8, 5, 0, tzinfo=timezone.utc),
    )
    result = await tools.call(ToolRequest(
        name="weather", arguments={"latitude": 37.5665, "longitude": 126.9780}, sku="weather", units=1,
    ))

    assert result.observation.status == "ok"
    assert result.observation.data.precipitation_probability == 67
