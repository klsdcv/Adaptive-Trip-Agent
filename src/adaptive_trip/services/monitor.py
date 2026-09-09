from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from adaptive_trip.agent.graph import Replanner
from adaptive_trip.domain.models import ChangeEvent, Observation, TripState, WeatherData
from adaptive_trip.storage.repository import Repository
from adaptive_trip.tools.contracts import ToolProvider, ToolRequest


class Monitor:
    def __init__(
        self,
        repository: Repository,
        tools: ToolProvider,
        *,
        clock: Callable[[], datetime],
        replanner: Replanner | None = None,
        rain_probability_threshold: int = 60,
        impact_window: timedelta = timedelta(minutes=60),
        check_interval: timedelta = timedelta(minutes=30),
    ) -> None:
        self._repository = repository
        self._tools = tools
        self._clock = clock
        self._replanner = replanner
        self._rain_probability_threshold = rain_probability_threshold
        self._impact_window = impact_window
        self._check_interval = check_interval

    async def tick(self) -> list[str]:
        now = self._clock()
        created_event_ids: list[str] = []
        for trip in self._repository.active_due_trips(now):
            try:
                if trip.position is None:
                    continue
                weather = await self._tools.call(
                    ToolRequest(
                        name="weather",
                        arguments={
                            "latitude": trip.position.latitude,
                            "longitude": trip.position.longitude,
                            "forecast_at": now.isoformat(),
                        },
                        sku="weather",
                        units=1,
                    )
                )
                event = self._weather_impact_event(trip, weather.observation, now)
                if event is None or not self._repository.save_event(event):
                    continue
                created_event_ids.append(event.id)
                if self._replanner is not None:
                    result = await self._replanner.run(trip, event, [weather.observation], now)
                    if result.proposal is not None:
                        self._repository.save_proposal(result.proposal)
            finally:
                self._repository.update_next_check(trip.id, now + self._check_interval)
        return created_event_ids

    def _weather_impact_event(
        self, trip: TripState, observation: Observation, now: datetime
    ) -> ChangeEvent | None:
        if observation.status != "ok" or not isinstance(observation.data, WeatherData):
            return None
        forecast = observation.data
        if forecast.precipitation_probability < self._rain_probability_threshold:
            return None
        affected = next(
            (
                item
                for item in trip.items
                if item.status != "completed"
                and item.rain_sensitive
                and now <= item.start <= now + self._impact_window
            ),
            None,
        )
        if affected is None:
            return None
        return ChangeEvent(
            id=str(uuid4()),
            trip_id=trip.id,
            kind="weather",
            at=now,
            affected_item_ids=(affected.id,),
            payload={
                "precipitation_probability": forecast.precipitation_probability,
                "forecast_at": forecast.forecast_at.isoformat(),
            },
            fingerprint=f"{trip.id}:{affected.id}:rain:{forecast.forecast_at.isoformat()}",
        )
