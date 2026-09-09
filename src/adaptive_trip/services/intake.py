from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from adaptive_trip.domain.models import Constraints, Coordinates, Item, PlacesData, TripState
from adaptive_trip.tools.contracts import ToolProvider, ToolRequest


class Draft(BaseModel):
    """A user-visible schedule draft that cannot change confirmed travel state yet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source_text: str
    items: list[Item] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confirmed: bool = False


class DraftItemInput(BaseModel):
    """User-confirmed item fields supplied before external place resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1)
    place_query: str = Field(min_length=1)
    activity_type: str = Field(min_length=1)
    start: AwareDatetime
    end: AwareDatetime
    fixed: bool
    rain_sensitive: bool = False


class ConfirmedDraftFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timezone: str
    search_origin: Coordinates
    items: list[DraftItemInput] = Field(min_length=1)


class IntakeService:
    def __init__(
        self,
        tools: ToolProvider | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._tools = tools
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._drafts: dict[str, Draft] = {}
        self._preferences: dict[str, dict[str, Any]] = {}
        self._confirmations: dict[tuple[str, str], TripState] = {}

    async def prepare(self, text: str | None, preferences: dict[str, object]) -> Draft:
        if text is None:
            raise ValueError("text must not be blank")
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text must not be blank")
        draft = Draft(
            id=str(uuid4()),
            source_text=cleaned,
            questions=["일정별 방문 시간과 여행 날짜를 알려주세요."],
            assumptions=[],
            confirmed=False,
        )
        self._drafts[draft.id] = draft
        self._preferences[draft.id] = dict(preferences)
        return draft

    async def confirm(
        self,
        draft_id: str,
        confirmed_fields: dict[str, object],
        request_id: str,
    ) -> TripState:
        if not request_id.strip():
            raise ValueError("request_id must not be blank")
        previous = self._confirmations.get((draft_id, request_id))
        if previous is not None:
            return previous
        if draft_id not in self._drafts:
            raise KeyError(draft_id)

        fields = ConfirmedDraftFields.model_validate(confirmed_fields)
        if self._tools is None:
            raise RuntimeError("Place lookup is unavailable.")

        resolved_items: list[Item] = []
        for item in fields.items:
            result = await self._tools.call(
                ToolRequest(
                    name="places_search",
                    arguments={
                        "query": item.place_query,
                        "latitude": fields.search_origin.latitude,
                        "longitude": fields.search_origin.longitude,
                    },
                    sku="places_text_search",
                    units=1,
                )
            )
            observation = result.observation
            if observation.status != "ok" or not isinstance(observation.data, PlacesData):
                raise ValueError(f"place could not be resolved: {item.place_query}")
            resolved_items.append(
                Item(
                    id=str(uuid4()),
                    place_id=observation.data.place_id,
                    title=item.title,
                    activity_type=item.activity_type,
                    start=item.start,
                    end=item.end,
                    status="pending",
                    fixed=item.fixed,
                    rain_sensitive=item.rain_sensitive,
                )
            )

        confirmed_at = self._clock()
        trip = TripState(
            id=str(uuid4()),
            version=0,
            timezone=fields.timezone,
            items=resolved_items,
            position=fields.search_origin,
            position_at=confirmed_at,
            now=confirmed_at,
            constraints=Constraints(preferences=self._preferences[draft_id]),
        )
        self._drafts[draft_id] = self._drafts[draft_id].model_copy(
            update={"items": resolved_items, "questions": [], "confirmed": True}
        )
        self._confirmations[(draft_id, request_id)] = trip
        return trip
