from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Money(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    amount: Annotated[Decimal, Field(ge=Decimal("0"))]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    certainty: Literal["confirmed", "estimated"]


class Coordinates(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_item_ids: frozenset[str] = frozenset()
    final_arrival_by: AwareDatetime | None = None
    hard_budget: Money | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    place_id: str
    title: str
    activity_type: str
    start: AwareDatetime
    end: AwareDatetime
    status: Literal["pending", "active", "completed"]
    fixed: bool
    cost: Money | None = None
    rain_sensitive: bool = False

    @model_validator(mode="after")
    def end_must_follow_start(self) -> Item:
        if self.end <= self.start:
            raise ValueError("item end must be after its start")
        return self


class PlacesData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    place_id: str
    display_name: str | None = None
    coordinates: Coordinates | None = None
    opening_intervals: list[tuple[AwareDatetime, AwareDatetime]] | None = None
    price: Money | None = None


class RouteData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    origin_place_id: str
    destination_place_id: str
    departure_at: AwareDatetime
    duration_seconds: Annotated[int, Field(ge=0)]
    distance_meters: Annotated[int, Field(ge=0)] | None = None


class WeatherData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    coordinates: Coordinates
    forecast_at: AwareDatetime
    precipitation_probability: Annotated[int, Field(ge=0, le=100)]


ObservationData = PlacesData | RouteData | WeatherData


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: Literal["place", "route", "weather"]
    status: Literal["ok", "missing", "unsupported", "error"]
    observed_at: AwareDatetime
    valid_until: AwareDatetime
    source: str
    data: ObservationData | None = None

    @model_validator(mode="after")
    def validity_must_follow_observation(self) -> Observation:
        if self.valid_until < self.observed_at:
            raise ValueError("observation validity must not precede observation time")
        if self.status == "ok" and self.data is None:
            raise ValueError("successful observation requires data")
        return self


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    status: Literal["pass", "fail", "unknown"]
    item_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    message: str


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    checks: list[Check]

    @property
    def eligible(self) -> bool:
        return all(check.status == "pass" for check in self.checks)


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    items: list[Item]
    rationale: str
    signature: str


class ChangeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    trip_id: str
    kind: Literal[
        "weather",
        "delay",
        "closed",
        "completion",
        "fatigue",
        "fixed",
        "preference",
        "position",
        "expense",
    ]
    at: AwareDatetime
    affected_item_ids: tuple[str, ...] = ()
    payload: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str


class TripState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: Annotated[int, Field(ge=0)]
    timezone: str
    items: list[Item]
    position: Coordinates | None = None
    position_at: AwareDatetime | None = None
    now: AwareDatetime
    spent: list[Money] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)
    travel_mode: bool = False

    @model_validator(mode="after")
    def validate_state(self) -> TripState:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a valid IANA timezone") from error

        if (self.position is None) != (self.position_at is None):
            raise ValueError("position and position_at must be supplied together")

        item_ids = [item.id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("item identifiers must be unique")

        return self


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    trip_id: str
    base_version: Annotated[int, Field(ge=0)]
    created_at: AwareDatetime
    expires_at: AwareDatetime
    candidates: list[Candidate]
    reports: dict[str, Report]
    status: Literal["pending", "accepted", "rejected", "stale"]
    reason: str


class DecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["applied", "rejected", "stale", "needs_confirmation", "invalid"]
    state: TripState
    proposal_id: str


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal: Proposal | None = None
    observations: list[Observation] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: int = 0
    model_calls: int = 0
    stop_reason: str
