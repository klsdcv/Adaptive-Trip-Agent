from __future__ import annotations

from datetime import timedelta

import pytest

from adaptive_trip.domain.models import Coordinates, Observation, WeatherData


@pytest.mark.asyncio
async def test_repeated_forecast_does_not_create_duplicate_weather_events(tmp_path, scenario) -> None:
    from adaptive_trip.services.monitor import Monitor
    from adaptive_trip.storage.repository import Repository
    from adaptive_trip.tools.synthetic import SyntheticTools

    loaded = scenario("rain")
    repository = Repository(tmp_path / "trip.db")
    repository.create(loaded.state)
    weather = Observation(
        id="rain-forecast",
        kind="weather",
        status="ok",
        observed_at=loaded.now,
        valid_until=loaded.now + timedelta(hours=2),
        source="synthetic",
        data=WeatherData(
            coordinates=Coordinates(latitude=34.6937, longitude=135.5023),
            forecast_at=loaded.now + timedelta(minutes=45),
            precipitation_probability=80,
        ),
    )
    monitor = Monitor(repository, SyntheticTools([weather]), clock=lambda: loaded.now)

    first = await monitor.tick()
    second = await monitor.tick()

    assert len(first) == 1
    assert second == []
