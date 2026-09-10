from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import ValidationError

from adaptive_trip.domain.models import (
    ChangeEvent,
    Coordinates,
    Money,
    TripState,
)


class EventValidationError(ValueError):
    pass


class EventConflictError(EventValidationError):
    pass


class TripEventService:
    """Validate user state events and derive the next immutable trip state."""

    def build(
        self,
        state: TripState,
        *,
        kind: str,
        payload: dict[str, object],
        expected_version: int,
        request_id: str,
        at: datetime,
    ) -> tuple[TripState, ChangeEvent]:
        if expected_version != state.version:
            raise EventConflictError("Trip state has changed; reload before sending this event.")
        if not request_id.strip():
            raise EventValidationError("request_id must not be blank")
        affected = self._affected_item_ids(state, kind, payload)
        updated = state
        if kind == "completion":
            updated = self._complete_items(state, affected)
        elif kind == "position":
            updated = self._update_position(state, payload, at)
        elif kind == "preference":
            updated = self._update_preferences(state, payload)
        elif kind == "expense":
            updated = self._add_expense(state, payload)
        elif kind == "fixed":
            updated = self._update_fixed(state, affected, payload)
        elif kind == "fatigue":
            updated = self._update_preferences(state, {"fatigue": payload})
        elif kind in {"weather", "delay", "closed"}:
            updated = state.model_copy(update={"now": at})
        else:
            raise EventValidationError(f"unsupported event kind: {kind}")
        updated = updated.model_copy(update={"version": state.version + 1, "now": at})
        event = ChangeEvent(
            id=str(uuid4()),
            trip_id=state.id,
            kind=kind,
            at=at,
            affected_item_ids=affected,
            payload=payload,
            fingerprint=f"{state.id}:{request_id}",
        )
        return updated, event

    @staticmethod
    def _affected_item_ids(
        state: TripState,
        kind: str,
        payload: dict[str, object],
    ) -> tuple[str, ...]:
        raw = payload.get("item_ids")
        if raw is None and "item_id" in payload:
            raw = [payload["item_id"]]
        if raw is None:
            return ()
        if not isinstance(raw, list) or not raw or not all(isinstance(value, str) for value in raw):
            raise EventValidationError("item_ids must be a non-empty list of strings")
        item_ids = tuple(dict.fromkeys(raw))
        known = {item.id for item in state.items}
        if any(item_id not in known for item_id in item_ids):
            raise EventValidationError("event references an unknown item")
        return item_ids

    @staticmethod
    def _complete_items(state: TripState, item_ids: tuple[str, ...]) -> TripState:
        if not item_ids:
            raise EventValidationError("completion requires item_ids")
        ids = set(item_ids)
        return state.model_copy(update={
            "items": [item.model_copy(update={"status": "completed"}) if item.id in ids else item for item in state.items]
        })

    @staticmethod
    def _update_position(state: TripState, payload: dict[str, object], at: datetime) -> TripState:
        try:
            coordinates = Coordinates(
                latitude=payload["latitude"],
                longitude=payload["longitude"],
            )
        except (KeyError, TypeError, ValidationError) as error:
            raise EventValidationError("position requires valid latitude and longitude") from error
        return state.model_copy(update={"position": coordinates, "position_at": at})

    @staticmethod
    def _update_preferences(state: TripState, payload: dict[str, object]) -> TripState:
        values = payload.get("preferences", payload)
        if not isinstance(values, dict):
            raise EventValidationError("preference event requires an object")
        travel_mode = values.get("travel_mode")
        preferences = {
            **state.constraints.preferences,
            **{key: value for key, value in values.items() if key != "travel_mode"},
        }
        constraints = state.constraints.model_copy(update={"preferences": preferences})
        update: dict[str, object] = {"constraints": constraints}
        if isinstance(travel_mode, bool):
            update["travel_mode"] = travel_mode
        return state.model_copy(update=update)

    @staticmethod
    def _add_expense(state: TripState, payload: dict[str, object]) -> TripState:
        try:
            expense = Money(
                amount=payload["amount"],
                currency=payload["currency"],
                certainty="confirmed",
            )
        except (KeyError, TypeError, ValidationError) as error:
            raise EventValidationError("expense requires amount and ISO currency") from error
        return state.model_copy(update={"spent": [*state.spent, expense]})

    @staticmethod
    def _update_fixed(
        state: TripState,
        item_ids: tuple[str, ...],
        payload: dict[str, object],
    ) -> TripState:
        if len(item_ids) != 1 or not isinstance(payload.get("fixed"), bool):
            raise EventValidationError("fixed event requires one item_id and a boolean fixed value")
        item_id = item_ids[0]
        return state.model_copy(update={
            "items": [item.model_copy(update={"fixed": payload["fixed"]}) if item.id == item_id else item for item in state.items]
        })
