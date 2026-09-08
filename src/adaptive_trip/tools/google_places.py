from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from adaptive_trip.domain.models import Coordinates, Observation, PlacesData, RouteData, WeatherData
from adaptive_trip.tools.contracts import ToolProvider, ToolRequest, ToolResult


PLACE_DETAILS_FIELDS = "id,displayName,location,currentOpeningHours"


class GoogleTools(ToolProvider):
    """Server-side adapter for the minimal Google Places data used by validation."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def call(self, request: ToolRequest) -> ToolResult:
        if request.name == "route":
            return await self._route(request)
        if request.name == "weather":
            return await self._weather(request)
        if request.name != "place_details":
            return self._unsupported(request, "unsupported_google_tool")

        place_id = request.arguments.get("place_id")
        if not isinstance(place_id, str) or not place_id or "/" in place_id:
            return self._unsupported(request, "invalid_place_id")

        response = await self._client.get(
            "https://places.googleapis.com/v1/places/" + quote(place_id, safe=":"),
            headers={
                "X-Goog-Api-Key": self._api_key,
                "X-Goog-FieldMask": PLACE_DETAILS_FIELDS,
            },
        )
        now = self._clock()
        if response.status_code != 200:
            return ToolResult(
                observation=Observation(
                    id=f"google:place:{place_id}", kind="place", status="error",
                    observed_at=now, valid_until=now + timedelta(minutes=5), source="google_places",
                ),
                attempts=1, error_code=f"http_{response.status_code}",
            )
        payload = response.json()
        location = payload.get("location")
        coordinates = None
        if isinstance(location, dict) and "latitude" in location and "longitude" in location:
            coordinates = Coordinates(latitude=location["latitude"], longitude=location["longitude"])
        return ToolResult(
            observation=Observation(
                id=f"google:place:{place_id}", kind="place", status="ok",
                observed_at=now, valid_until=now + timedelta(hours=1), source="google_places",
                data=PlacesData(place_id=payload.get("id", place_id), coordinates=coordinates),
            ),
            attempts=1,
        )

    async def _route(self, request: ToolRequest) -> ToolResult:
        origin = request.arguments.get("origin_place_id")
        destination = request.arguments.get("destination_place_id")
        departure_at = request.arguments.get("departure_at")
        if not all(isinstance(value, str) and value for value in (origin, destination, departure_at)):
            return self._unsupported(request, "invalid_route_request")
        try:
            departure = datetime.fromisoformat(departure_at)
        except ValueError:
            return self._unsupported(request, "invalid_departure_at")
        response = await self._client.post(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            headers={"X-Goog-Api-Key": self._api_key, "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"},
            json={"origin": {"placeId": origin}, "destination": {"placeId": destination}, "travelMode": "WALK"},
        )
        now = self._clock()
        routes = response.json().get("routes", []) if response.status_code == 200 else []
        if not routes or not isinstance(routes[0].get("duration"), str):
            return ToolResult(
                observation=Observation(id="google:route", kind="route", status="missing", observed_at=now,
                                        valid_until=now + timedelta(minutes=5), source="google_routes"),
                attempts=1, error_code=f"http_{response.status_code}",
            )
        duration = int(routes[0]["duration"].removesuffix("s"))
        return ToolResult(
            observation=Observation(
                id="google:route", kind="route", status="ok", observed_at=now,
                valid_until=departure, source="google_routes",
                data=RouteData(origin_place_id=origin, destination_place_id=destination, departure_at=departure,
                               duration_seconds=duration, distance_meters=routes[0].get("distanceMeters")),
            ), attempts=1,
        )

    async def _weather(self, request: ToolRequest) -> ToolResult:
        latitude = request.arguments.get("latitude")
        longitude = request.arguments.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            return self._unsupported(request, "invalid_coordinates")
        response = await self._client.get(
            "https://weather.googleapis.com/v1/forecast/hours:lookup",
            params={"location.latitude": latitude, "location.longitude": longitude, "hours": 1, "key": self._api_key},
        )
        now = self._clock()
        if response.status_code == 404:
            return ToolResult(
                observation=Observation(id="google:weather", kind="weather", status="unsupported", observed_at=now,
                                        valid_until=now + timedelta(minutes=30), source="google_weather"),
                attempts=1, error_code="unsupported_location",
            )
        hours = response.json().get("forecastHours", []) if response.status_code == 200 else []
        if not hours:
            return ToolResult(
                observation=Observation(id="google:weather", kind="weather", status="missing", observed_at=now,
                                        valid_until=now + timedelta(minutes=30), source="google_weather"),
                attempts=1, error_code=f"http_{response.status_code}",
            )
        forecast = hours[0]
        start = forecast.get("interval", {}).get("startTime", now.isoformat())
        probability = forecast.get("precipitation", {}).get("probability", {}).get("percent", 0)
        forecast_at = datetime.fromisoformat(start.replace("Z", "+00:00"))
        return ToolResult(
            observation=Observation(
                id="google:weather", kind="weather", status="ok", observed_at=now,
                valid_until=now + timedelta(minutes=30), source="google_weather",
                data=WeatherData(coordinates=Coordinates(latitude=latitude, longitude=longitude), forecast_at=forecast_at,
                                 precipitation_probability=probability),
            ), attempts=1,
        )

    def _unsupported(self, request: ToolRequest, error_code: str) -> ToolResult:
        now = self._clock()
        return ToolResult(
            observation=Observation(
                id=f"google:{request.name}", kind="place", status="unsupported",
                observed_at=now, valid_until=now + timedelta(minutes=1), source="google_places",
            ),
            attempts=1, error_code=error_code,
        )
