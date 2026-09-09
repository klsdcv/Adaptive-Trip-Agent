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


@pytest.mark.asyncio
async def test_confirm_interprets_naive_form_times_in_the_trip_timezone() -> None:
    from adaptive_trip.services.intake import IntakeService

    now = datetime(2026, 9, 9, tzinfo=timezone.utc)

    class PlaceTools:
        async def call(self, request):
            return ToolResult(
                observation=Observation(
                    id="place-local-time",
                    kind="place",
                    status="ok",
                    observed_at=now,
                    valid_until=now + timedelta(hours=1),
                    source="test",
                    data=PlacesData(place_id="google-place-local-time"),
                ),
                attempts=1,
            )

    service = IntakeService(tools=PlaceTools(), clock=lambda: now)
    draft = await service.prepare("오사카성", {})
    trip = await service.confirm(
        draft.id,
        {
            "timezone": "Asia/Tokyo",
            "search_origin": {"latitude": 34.6937, "longitude": 135.5023},
            "items": [{
                "title": "오사카성",
                "place_query": "오사카성",
                "activity_type": "sightseeing",
                "start": "2026-09-10T10:00",
                "end": "2026-09-10T12:00",
                "fixed": False,
            }],
        },
        request_id="local-time",
    )

    assert trip.items[0].start.isoformat() == "2026-09-10T10:00:00+09:00"


@pytest.mark.asyncio
async def test_draft_and_confirmation_survive_service_restart(tmp_path) -> None:
    from adaptive_trip.services.intake import IntakeService
    from adaptive_trip.storage.repository import Repository

    now = datetime(2026, 9, 9, tzinfo=timezone.utc)

    class CountingTools:
        def __init__(self) -> None:
            self.calls = 0

        async def call(self, request):
            self.calls += 1
            return ToolResult(
                observation=Observation(
                    id="persistent-place",
                    kind="place",
                    status="ok",
                    observed_at=now,
                    valid_until=now + timedelta(hours=1),
                    source="test",
                    data=PlacesData(place_id="persistent-google-place"),
                ),
                attempts=1,
            )

    repository = Repository(tmp_path / "trip.db")
    tools = CountingTools()
    first_service = IntakeService(tools=tools, repository=repository, clock=lambda: now)
    draft = await first_service.prepare("후쿠오카 타워", {"pace": "slow"})
    fields = {
        "timezone": "Asia/Tokyo",
        "search_origin": {"latitude": 33.5902, "longitude": 130.4017},
        "items": [{
            "title": "후쿠오카 타워",
            "place_query": "후쿠오카 타워",
            "activity_type": "sightseeing",
            "start": "2026-09-10T10:00",
            "end": "2026-09-10T12:00",
            "fixed": False,
        }],
    }

    restarted_service = IntakeService(tools=tools, repository=repository, clock=lambda: now)
    first_trip = await restarted_service.confirm(
        draft.id, fields, request_id="persistent-confirmation"
    )
    another_restart = IntakeService(tools=tools, repository=repository, clock=lambda: now)
    repeated_trip = await another_restart.confirm(
        draft.id, fields, request_id="persistent-confirmation"
    )

    assert repository.get(first_trip.id) == first_trip
    assert repeated_trip == first_trip
    assert tools.calls == 1


@pytest.mark.asyncio
async def test_prepare_uses_parser_to_create_multiple_draft_items() -> None:
    from adaptive_trip.services.intake import (
        DraftItem,
        IntakeService,
        ParsedDraft,
    )

    class TwoItemParser:
        async def parse(self, text, preferences, reference_time):
            return ParsedDraft(
                items=[
                    DraftItem(
                        id="draft-item-1",
                        title="오사카성",
                        place_query="오사카성",
                        activity_type="sightseeing",
                        start="2026-09-10T10:00",
                        end="2026-09-10T12:00",
                        fixed=False,
                        rain_sensitive=True,
                    ),
                    DraftItem(
                        id="draft-item-2",
                        title="도톤보리 저녁",
                        place_query="도톤보리 오사카",
                        activity_type="dinner",
                        start="2026-09-10T19:00",
                        end="2026-09-10T20:30",
                        fixed=True,
                        rain_sensitive=False,
                    ),
                ],
                questions=[],
                assumptions=["저녁 식사 체류시간을 90분으로 추정했습니다."],
            )

    service = IntakeService(parser=TwoItemParser())
    draft = await service.prepare(
        "9월 10일 10시 오사카성, 19시 도톤보리 저녁 예약",
        {},
    )

    assert [item.title for item in draft.items] == ["오사카성", "도톤보리 저녁"]
    assert draft.items[1].fixed is True
    assert draft.assumptions == ["저녁 식사 체류시간을 90분으로 추정했습니다."]


@pytest.mark.asyncio
async def test_confirm_uses_first_resolved_place_as_trip_location() -> None:
    from adaptive_trip.services.intake import IntakeService

    now = datetime(2026, 9, 9, tzinfo=timezone.utc)

    class PlaceTools:
        def __init__(self) -> None:
            self.arguments = []

        async def call(self, request):
            self.arguments.append(request.arguments)
            coordinates = Coordinates(latitude=34.6873, longitude=135.5262)
            return ToolResult(
                observation=Observation(
                    id=f"place-{len(self.arguments)}",
                    kind="place",
                    status="ok",
                    observed_at=now,
                    valid_until=now + timedelta(hours=1),
                    source="test",
                    data=PlacesData(
                        place_id=f"google-place-{len(self.arguments)}",
                        coordinates=coordinates,
                    ),
                ),
                attempts=1,
            )

    tools = PlaceTools()
    service = IntakeService(tools=tools, clock=lambda: now)
    draft = await service.prepare("오사카성, 도톤보리", {})
    trip = await service.confirm(
        draft.id,
        {
            "timezone": "Asia/Tokyo",
            "items": [
                {
                    "title": "오사카성", "place_query": "오사카성",
                    "activity_type": "sightseeing", "start": "2026-09-10T10:00",
                    "end": "2026-09-10T12:00", "fixed": False,
                },
                {
                    "title": "도톤보리", "place_query": "도톤보리 오사카",
                    "activity_type": "dinner", "start": "2026-09-10T19:00",
                    "end": "2026-09-10T20:30", "fixed": False,
                },
            ],
        },
        request_id="automatic-location",
    )

    assert tools.arguments[0] == {"query": "오사카성"}
    assert tools.arguments[1] == {
        "query": "도톤보리 오사카", "latitude": 34.6873, "longitude": 135.5262,
    }
    assert trip.position == Coordinates(latitude=34.6873, longitude=135.5262)
