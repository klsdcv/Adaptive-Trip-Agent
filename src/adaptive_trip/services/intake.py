from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Annotated, Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field

from adaptive_trip.domain.models import Constraints, Coordinates, Item, PlacesData, TripState
from adaptive_trip.tools.contracts import ToolProvider, ToolRequest

if TYPE_CHECKING:
    from adaptive_trip.storage.repository import Repository


LocalDateTime = Annotated[
    str,
    Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$"),
]


class DraftItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str = Field(min_length=1)
    place_query: str = Field(min_length=1)
    activity_type: str = Field(min_length=1)
    start: LocalDateTime | None
    end: LocalDateTime | None
    fixed: bool
    rain_sensitive: bool


class ParsedDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[DraftItem] = Field(max_length=20)
    questions: list[str] = Field(max_length=20)
    assumptions: list[str] = Field(max_length=20)


class IntakeParser(Protocol):
    async def parse(
        self,
        text: str,
        preferences: dict[str, object],
        reference_time: datetime,
    ) -> ParsedDraft: ...


class ManualIntakeParser:
    async def parse(
        self,
        text: str,
        preferences: dict[str, object],
        reference_time: datetime,
    ) -> ParsedDraft:
        del text, preferences, reference_time
        return ParsedDraft(
            items=[],
            questions=["일정별 방문 시간과 여행 날짜를 알려주세요."],
            assumptions=[],
        )


class Draft(BaseModel):
    """A user-visible schedule draft that cannot change confirmed travel state yet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source_text: str
    items: list[DraftItem] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confirmed: bool = False


class DraftItemInput(BaseModel):
    """User-confirmed item fields supplied before external place resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1)
    place_query: str = Field(min_length=1)
    activity_type: str = Field(min_length=1)
    start: datetime
    end: datetime
    fixed: bool
    rain_sensitive: bool = False


class ConfirmedDraftFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timezone: str
    search_origin: Coordinates | None = None
    items: list[DraftItemInput] = Field(min_length=1)


class IntakeService:
    def __init__(
        self,
        tools: ToolProvider | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        repository: Repository | None = None,
        parser: IntakeParser | None = None,
    ) -> None:
        self._tools = tools
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._repository = repository
        self._parser = parser or ManualIntakeParser()
        self._drafts: dict[str, Draft] = {}
        self._preferences: dict[str, dict[str, Any]] = {}
        self._confirmations: dict[tuple[str, str], TripState] = {}

    async def prepare(self, text: str | None, preferences: dict[str, object]) -> Draft:
        if text is None:
            raise ValueError("text must not be blank")
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text must not be blank")
        parsed = await self._parser.parse(cleaned, preferences, self._clock())
        draft = Draft(
            id=str(uuid4()),
            source_text=cleaned,
            items=parsed.items,
            questions=parsed.questions,
            assumptions=parsed.assumptions,
            confirmed=False,
        )
        self._drafts[draft.id] = draft
        self._preferences[draft.id] = dict(preferences)
        if self._repository is not None:
            self._repository.save_draft(
                draft.id,
                draft.model_dump_json(),
                json.dumps(preferences, ensure_ascii=False),
            )
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
        if self._repository is not None:
            try:
                return self._repository.get_draft_confirmation(draft_id, request_id)
            except KeyError:
                pass
        if draft_id not in self._drafts:
            if self._repository is None:
                raise KeyError(draft_id)
            draft_json, preferences_json = self._repository.get_draft(draft_id)
            self._drafts[draft_id] = Draft.model_validate_json(draft_json)
            self._preferences[draft_id] = json.loads(preferences_json)

        fields = ConfirmedDraftFields.model_validate(confirmed_fields)
        try:
            trip_timezone = ZoneInfo(fields.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        if self._tools is None:
            raise RuntimeError("Place lookup is unavailable.")

        resolved_items: list[Item] = []
        search_origin = fields.search_origin
        for item in fields.items:
            arguments: dict[str, object] = {"query": item.place_query}
            if search_origin is not None:
                arguments.update(
                    latitude=search_origin.latitude,
                    longitude=search_origin.longitude,
                )
            result = await self._tools.call(
                ToolRequest(
                    name="places_search",
                    arguments=arguments,
                    sku="places_text_search",
                    units=1,
                )
            )
            observation = result.observation
            if observation.status != "ok" or not isinstance(observation.data, PlacesData):
                raise ValueError(f"place could not be resolved: {item.place_query}")
            if search_origin is None:
                if observation.data.coordinates is None:
                    raise ValueError("first resolved place did not include coordinates")
                search_origin = observation.data.coordinates
            start = item.start if item.start.tzinfo is not None else item.start.replace(tzinfo=trip_timezone)
            end = item.end if item.end.tzinfo is not None else item.end.replace(tzinfo=trip_timezone)
            resolved_items.append(
                Item(
                    id=str(uuid4()),
                    place_id=observation.data.place_id,
                    title=item.title,
                    activity_type=item.activity_type,
                    start=start,
                    end=end,
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
            position=search_origin,
            position_at=confirmed_at,
            now=confirmed_at,
            constraints=Constraints(preferences=self._preferences[draft_id]),
        )
        confirmed_draft = self._drafts[draft_id].model_copy(
            update={"questions": [], "confirmed": True}
        )
        self._drafts[draft_id] = confirmed_draft
        if self._repository is not None:
            trip = self._repository.confirm_draft(
                draft_id=draft_id,
                request_id=request_id,
                draft_json=confirmed_draft.model_dump_json(),
                state=trip,
            )
        self._confirmations[(draft_id, request_id)] = trip
        return trip
