from __future__ import annotations

import pytest

from adaptive_trip.domain.models import Item, Money, TripState


def test_naive_current_time_is_rejected() -> None:
    raw_state = {
        "id": "trip-001",
        "version": 1,
        "timezone": "Asia/Tokyo",
        "items": [],
        "position": None,
        "position_at": None,
        "now": "2026-09-08T14:30:00",
        "spent": [],
        "constraints": {},
        "travel_mode": False,
    }

    with pytest.raises(ValueError):
        TripState.model_validate(raw_state)


def test_item_rejects_an_end_before_its_start() -> None:
    with pytest.raises(ValueError):
        Item.model_validate(
            {
                "id": "museum",
                "place_id": "synthetic:museum",
                "title": "Museum",
                "activity_type": "indoor",
                "start": "2026-09-08T16:00:00+09:00",
                "end": "2026-09-08T15:30:00+09:00",
                "status": "pending",
                "fixed": False,
            }
        )


@pytest.mark.parametrize("amount", ["-1", "-0.01"])
def test_money_rejects_a_negative_amount(amount: str) -> None:
    with pytest.raises(ValueError):
        Money.model_validate(
            {"amount": amount, "currency": "JPY", "certainty": "estimated"}
        )


def test_trip_state_requires_position_timestamp_with_position() -> None:
    with pytest.raises(ValueError):
        TripState.model_validate(
            {
                "id": "trip-001",
                "version": 1,
                "timezone": "Asia/Tokyo",
                "items": [],
                "position": {"latitude": 34.7, "longitude": 135.5},
                "position_at": None,
                "now": "2026-09-08T14:30:00+09:00",
                "spent": [],
                "constraints": {},
                "travel_mode": False,
            }
        )


def test_rain_scenario_is_loaded_as_an_independent_state(scenario) -> None:
    first = scenario("rain")
    second = scenario("rain")

    assert first.state.id == "synthetic-rain-trip"
    assert first.state.items[0].status == "completed"
    assert first.state is not second.state
