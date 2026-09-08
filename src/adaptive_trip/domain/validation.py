from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from adaptive_trip.domain.models import (
    Candidate,
    Check,
    Item,
    Observation,
    PlacesData,
    Report,
    RouteData,
    TripState,
)


def validate(
    state: TripState,
    candidate: Candidate,
    observations: list[Observation],
    now: datetime,
) -> Report:
    """Return deterministic checks for a proposed, not-yet-applied schedule."""
    checks: list[Check] = []
    candidate_by_id = {item.id: item for item in candidate.items}
    state_by_id = {item.id: item for item in state.items}

    checks.extend(_check_fixed_and_required_items(state, candidate_by_id))
    checks.extend(_check_completed_items(state, candidate_by_id))
    checks.extend(_check_schedule_order(candidate.items))
    checks.extend(_check_routes(candidate.items, observations, now))
    checks.extend(_check_opening_hours(candidate.items, observations))
    checks.extend(_check_budget(state, candidate.items))
    checks.extend(_check_final_arrival(state, candidate.items))

    return Report(checks=checks)


def _check_fixed_and_required_items(
    state: TripState, candidate_by_id: dict[str, Item]
) -> list[Check]:
    checks: list[Check] = []
    for original in state.items:
        if not original.fixed:
            continue
        replacement = candidate_by_id.get(original.id)
        if replacement is None:
            checks.append(
                Check(
                    code="fixed_item",
                    status="fail",
                    item_id=original.id,
                    message="A fixed itinerary item is missing from the proposal.",
                )
            )
        elif replacement.start != original.start or replacement.end != original.end:
            checks.append(
                Check(
                    code="fixed_time",
                    status="fail",
                    item_id=original.id,
                    message="A fixed itinerary item changed its scheduled time.",
                )
            )
        else:
            checks.append(
                Check(
                    code="fixed_item",
                    status="pass",
                    item_id=original.id,
                    message="The fixed itinerary item is preserved.",
                )
            )

    for item_id in state.constraints.required_item_ids:
        checks.append(
            Check(
                code="required_item",
                status="pass" if item_id in candidate_by_id else "fail",
                item_id=item_id,
                message=(
                    "The required itinerary item is present."
                    if item_id in candidate_by_id
                    else "A required itinerary item is missing from the proposal."
                ),
            )
        )
    return checks


def _check_completed_items(state: TripState, candidate_by_id: dict[str, Item]) -> list[Check]:
    checks: list[Check] = []
    for original in state.items:
        if original.status != "completed":
            continue
        replacement = candidate_by_id.get(original.id)
        unchanged = replacement == original
        checks.append(
            Check(
                code="completed_item",
                status="pass" if unchanged else "fail",
                item_id=original.id,
                message=(
                    "The completed itinerary item is preserved."
                    if unchanged
                    else "A completed itinerary item changed or was removed."
                ),
            )
        )
    return checks


def _check_schedule_order(items: list[Item]) -> list[Check]:
    ordered = sorted(items, key=lambda item: item.start)
    checks: list[Check] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        checks.append(
            Check(
                code="overlap",
                status="pass" if previous.end <= current.start else "fail",
                item_id=current.id,
                message=(
                    "The itinerary items do not overlap."
                    if previous.end <= current.start
                    else "The itinerary item overlaps the preceding item."
                ),
            )
        )
    return checks


def _check_routes(
    items: list[Item], observations: list[Observation], now: datetime
) -> list[Check]:
    ordered = [item for item in sorted(items, key=lambda item: item.start) if item.end >= now]
    route_observations = [
        observation
        for observation in observations
        if observation.kind == "route" and isinstance(observation.data, RouteData)
    ]
    checks: list[Check] = []
    for origin, destination in zip(ordered, ordered[1:], strict=False):
        departure_at = max(origin.end, now)
        route = _find_route(route_observations, origin.place_id, destination.place_id, departure_at)
        if route is None:
            checks.append(
                Check(
                    code="route",
                    status="unknown",
                    item_id=destination.id,
                    message="The route duration for this itinerary leg is not confirmed.",
                )
            )
            continue
        arrival = departure_at + timedelta(seconds=route.data.duration_seconds)
        checks.append(
            Check(
                code="route",
                status="pass" if arrival <= destination.start else "fail",
                item_id=destination.id,
                evidence_ids=(route.id,),
                message=(
                    "The route arrives before the next itinerary item."
                    if arrival <= destination.start
                    else "The route arrives after the next itinerary item starts."
                ),
            )
        )
    return checks


def _find_route(
    observations: list[Observation], origin_place_id: str, destination_place_id: str, departure_at: datetime
) -> Observation | None:
    matches = [
        observation
        for observation in observations
        if observation.status == "ok"
        and isinstance(observation.data, RouteData)
        and observation.data.origin_place_id == origin_place_id
        and observation.data.destination_place_id == destination_place_id
        and observation.data.departure_at == departure_at
        and observation.valid_until >= departure_at
    ]
    return max(matches, key=lambda observation: observation.observed_at, default=None)


def _check_opening_hours(items: list[Item], observations: list[Observation]) -> list[Check]:
    place_observations = [
        observation
        for observation in observations
        if observation.kind == "place" and isinstance(observation.data, PlacesData)
    ]
    checks: list[Check] = []
    for item in items:
        if item.status == "completed":
            continue
        observation = next(
            (
                value
                for value in place_observations
                if value.status == "ok"
                and isinstance(value.data, PlacesData)
                and value.data.place_id == item.place_id
            ),
            None,
        )
        if observation is None or observation.data.opening_intervals is None:
            checks.append(
                Check(
                    code="opening_hours",
                    status="unknown",
                    item_id=item.id,
                    message="Opening hours for this itinerary item are not confirmed.",
                )
            )
            continue
        is_open = any(start <= item.start and item.end <= end for start, end in observation.data.opening_intervals)
        checks.append(
            Check(
                code="opening_hours",
                status="pass" if is_open else "fail",
                item_id=item.id,
                evidence_ids=(observation.id,),
                message=(
                    "The itinerary item is within confirmed opening hours."
                    if is_open
                    else "The itinerary item is outside confirmed opening hours."
                ),
            )
        )
    return checks


def _check_budget(state: TripState, items: list[Item]) -> list[Check]:
    budget = state.constraints.hard_budget
    if budget is None:
        return []
    amounts = [
        *state.spent,
        *(
            item.cost
            for item in items
            if item.status != "completed" and item.cost is not None
        ),
    ]
    if any(amount.currency != budget.currency for amount in amounts):
        return [
            Check(
                code="budget",
                status="unknown",
                message="Budget currencies cannot be compared without a confirmed exchange rate.",
            )
        ]
    if any(amount.certainty == "estimated" for amount in amounts):
        return [
            Check(
                code="budget",
                status="unknown",
                message="The total budget includes estimated costs.",
            )
        ]
    total = sum((amount.amount for amount in amounts), Decimal("0"))
    return [
        Check(
            code="budget",
            status="pass" if total <= budget.amount else "fail",
            message="The confirmed cost is within budget." if total <= budget.amount else "The confirmed cost exceeds budget.",
        )
    ]


def _check_final_arrival(state: TripState, items: list[Item]) -> list[Check]:
    deadline = state.constraints.final_arrival_by
    if deadline is None:
        return []
    latest_end = max((item.end for item in items), default=None)
    if latest_end is None:
        return [Check(code="final_arrival", status="unknown", message="No final itinerary item is available.")]
    return [
        Check(
            code="final_arrival",
            status="pass" if latest_end <= deadline else "fail",
            message=(
                "The itinerary finishes before the final arrival deadline."
                if latest_end <= deadline
                else "The itinerary finishes after the final arrival deadline."
            ),
        )
    ]
