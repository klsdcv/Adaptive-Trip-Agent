from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import httpx

from adaptive_trip.domain.models import Coordinates, Observation, WeatherData
from adaptive_trip.tools.contracts import ToolProvider, ToolRequest, ToolResult


class OpenMeteoTools(ToolProvider):
    """Keyless global weather adapter, including locations unsupported by Google Weather."""

    def __init__(self, client: httpx.AsyncClient, *, clock: Callable[[], datetime] | None = None) -> None:
        self._client = client
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def call(self, request: ToolRequest) -> ToolResult:
        now = self._clock()
        latitude = request.arguments.get("latitude")
        longitude = request.arguments.get("longitude")
        if request.name != "weather" or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            return ToolResult(
                observation=Observation(id="open_meteo:unsupported", kind="weather", status="unsupported", observed_at=now,
                                        valid_until=now + timedelta(minutes=1), source="open_meteo"),
                attempts=1, error_code="invalid_weather_request",
            )
        response = await self._client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": latitude, "longitude": longitude,
                    "hourly": "precipitation_probability,rain,weather_code", "forecast_days": 2, "timezone": "GMT"},
        )
        hourly = response.json().get("hourly", {}) if response.status_code == 200 else {}
        times = hourly.get("time", [])
        probabilities = hourly.get("precipitation_probability", [])
        if not times or not probabilities:
            return ToolResult(
                observation=Observation(id="open_meteo:weather", kind="weather", status="missing", observed_at=now,
                                        valid_until=now + timedelta(minutes=30), source="open_meteo"),
                attempts=1, error_code=f"http_{response.status_code}",
            )
        target = request.arguments.get('forecast_at', now.isoformat())
        target = datetime.fromisoformat(target.replace('Z', '+00:00'))
        if target.tzinfo is None:
            raise ValueError('forecast_at requires a timezone')
        selected = next((
            (datetime.fromisoformat(value).replace(tzinfo=timezone.utc), probability)
            for value, probability in zip(times, probabilities)
            if datetime.fromisoformat(value).replace(tzinfo=timezone.utc) <= target
            < datetime.fromisoformat(value).replace(tzinfo=timezone.utc) + timedelta(hours=1)
            and isinstance(probability, int) and not isinstance(probability, bool) and 0 <= probability <= 100
        ), None)
        if selected is None:
            return ToolResult(observation=Observation(
                id='open_meteo:weather', kind='weather', status='missing', observed_at=now,
                valid_until=now + timedelta(minutes=30), source='open_meteo'),
                attempts=1, error_code='missing_forecast')
        forecast_at, probability = selected
        return ToolResult(
            observation=Observation(
                id="open_meteo:weather", kind="weather", status="ok", observed_at=now,
                valid_until=now + timedelta(minutes=30), source="open_meteo",
                data=WeatherData(coordinates=Coordinates(latitude=latitude, longitude=longitude), forecast_at=forecast_at,
                                 precipitation_probability=probability),
            ), attempts=1,
        )
