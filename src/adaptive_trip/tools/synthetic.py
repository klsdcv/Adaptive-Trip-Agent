from __future__ import annotations

from datetime import datetime, timedelta, timezone

from adaptive_trip.domain.models import Observation, RouteData, WeatherData
from adaptive_trip.tools.contracts import ToolProvider, ToolRequest, ToolResult


class SyntheticTools(ToolProvider):
    def __init__(self, observations: list[Observation]) -> None:
        self._observations = list(observations)

    async def call(self, request: ToolRequest) -> ToolResult:
        observation = self._matching_observation(request)
        if observation is not None:
            return ToolResult(observation=observation, attempts=1)
        now = datetime.now(timezone.utc)
        return ToolResult(
            observation=Observation(
                id=f"synthetic:missing:{request.name}",
                kind=_observation_kind(request.name),
                status="missing",
                observed_at=now,
                valid_until=now + timedelta(minutes=1),
                source="synthetic",
            ),
            attempts=1,
            error_code="missing_fixture",
        )

    def _matching_observation(self, request: ToolRequest) -> Observation | None:
        for observation in self._observations:
            if request.name == "route" and isinstance(observation.data, RouteData):
                if (
                    observation.data.origin_place_id == request.arguments.get("origin_place_id")
                    and observation.data.destination_place_id
                    == request.arguments.get("destination_place_id")
                ):
                    return observation
            if request.name == "weather" and isinstance(observation.data, WeatherData):
                coordinates = observation.data.coordinates
                if (
                    coordinates.latitude == request.arguments.get("latitude")
                    and coordinates.longitude == request.arguments.get("longitude")
                ):
                    return observation
            if request.name in {"places_search", "place_details"} and observation.kind == "place":
                if observation.data is not None and getattr(observation.data, "place_id", None) == request.arguments.get("place_id"):
                    return observation
        return None


def _observation_kind(name: str) -> Literal["place", "route", "weather"]:
    if name == "route":
        return "route"
    if name == "weather":
        return "weather"
    return "place"
