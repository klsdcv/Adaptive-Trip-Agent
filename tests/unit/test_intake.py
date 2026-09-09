from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from adaptive_trip.domain.models import Coordinates, Observation, PlacesData
from adaptive_trip.tools.contracts import ToolResult


@pytest.mark.asyncio
async def test_free_text_without_time_becomes_an_unconfirmed_draft() -> None:
    from adaptive_trip.services.intake import IntakeService

    draft = await IntakeService().prepare("내일 미술관 갔다가 저녁", {})

    assert not draft.confirmed
    assert draft.items == []
    assert "시간" in draft.questions[0]


@pytest.mark.asyncio
async def test_blank_text_is_rejected() -> None:
    from adaptive_trip.services.intake import IntakeService

    with pytest.raises(ValueError, match="text"):
        await IntakeService().prepare("   ", {})


@pytest.mark.asyncio
async def test_confirm_resolves_place_queries_before_creating_trip_items() -> None:
    from adaptive_trip.services.intake import IntakeService

    now = datetime(2026, 9, 9, tzinfo=timezone.utc)

    class PlaceTools:
        def __init__(self) -> None:
            self.requests = []

        async def call(self, request):
            self.requests.append(request)
            return ToolResult(
                observation=Observation(
                    id="google:search:national-museum",
                    kind="place",
                    status="ok",
                    observed_at=now,
                    valid_until=now + timedelta(hours=1),
                    source="google_places",
                    data=PlacesData(
                        place_id="ChIJ-real-google-place-id",
                        display_name="국립중앙박물관",
                        coordinates=Coordinates(latitude=37.5239, longitude=126.9803),
                    ),
                ),
                attempts=1,
            )

    tools = PlaceTools()
    service = IntakeService(tools=tools, clock=lambda: now)
    draft = await service.prepare("내일 국립중앙박물관", {"pace": "relaxed"})

    trip = await service.confirm(
        draft.id,
        {
            "timezone": "Asia/Seoul",
            "search_origin": {"latitude": 37.5665, "longitude": 126.9780},
            "items": [
                {
                    "title": "국립중앙박물관",
                    "place_query": "국립중앙박물관 서울",
                    "activity_type": "museum",
                    "start": "2026-09-10T10:00:00+09:00",
                    "end": "2026-09-10T12:00:00+09:00",
                    "fixed": False,
                }
            ],
        },
        request_id="confirm-1",
    )

    assert trip.items[0].place_id == "ChIJ-real-google-place-id"
    assert trip.constraints.preferences == {"pace": "relaxed"}
    assert tools.requests[0].name == "places_search"
    assert tools.requests[0].arguments == {
        "query": "국립중앙박물관 서울",
        "latitude": 37.5665,
        "longitude": 126.978,
    }


@pytest.mark.asyncio
async def test_confirm_rejects_a_draft_without_items() -> None:
    from adaptive_trip.services.intake import IntakeService

    service = IntakeService()
    draft = await service.prepare("내일 미술관", {})

    with pytest.raises(ValueError, match="item"):
        await service.confirm(
            draft.id,
            {"timezone": "Asia/Seoul", "items": []},
            request_id="confirm-empty",
        )


@pytest.mark.asyncio
async def test_confirm_is_idempotent_for_the_same_request_id() -> None:
    from adaptive_trip.services.intake import IntakeService

    now = datetime(2026, 9, 9, tzinfo=timezone.utc)

    class CountingTools:
        def __init__(self) -> None:
            self.calls = 0

        async def call(self, request):
            self.calls += 1
            return ToolResult(
                observation=Observation(
                    id="place-1",
                    kind="place",
                    status="ok",
                    observed_at=now,
                    valid_until=now + timedelta(hours=1),
                    source="test",
                    data=PlacesData(place_id="google-place-1"),
                ),
                attempts=1,
            )

    tools = CountingTools()
    service = IntakeService(tools=tools, clock=lambda: now)
    draft = await service.prepare("내일 미술관", {})
    fields = {
        "timezone": "Asia/Seoul",
        "search_origin": {"latitude": 37.5665, "longitude": 126.9780},
        "items": [{
            "title": "미술관",
            "place_query": "서울 미술관",
            "activity_type": "museum",
            "start": "2026-09-10T10:00:00+09:00",
            "end": "2026-09-10T12:00:00+09:00",
            "fixed": False,
        }],
    }

    first = await service.confirm(draft.id, fields, request_id="same-request")
    second = await service.confirm(draft.id, fields, request_id="same-request")

    assert second == first
    assert tools.calls == 1
