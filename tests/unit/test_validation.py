from __future__ import annotations

from adaptive_trip.domain.models import Candidate, Constraints, Money


def test_unknown_route_is_not_eligible(scenario) -> None:
    from adaptive_trip.domain.validation import validate

    loaded = scenario("rain")
    candidate = Candidate(
        id="candidate-with-unverified-route",
        items=loaded.state.items,
        rationale="Keep the current schedule until a route is confirmed.",
        signature="synthetic:park|outdoor",
    )

    report = validate(loaded.state, candidate, [], loaded.now)

    assert not report.eligible
    assert any(check.code == "route" and check.status == "unknown" for check in report.checks)


def test_missing_fixed_item_fails_validation(scenario) -> None:
    from adaptive_trip.domain.validation import validate

    loaded = scenario("rain")
    candidate = Candidate(
        id="candidate-without-booking",
        items=loaded.state.items[:-1],
        rationale="This accidentally drops dinner.",
        signature="synthetic:park|outdoor",
    )

    report = validate(loaded.state, candidate, [], loaded.now)

    assert any(check.code == "fixed_item" and check.status == "fail" for check in report.checks)


def test_completed_item_cost_is_not_counted_twice_in_budget(scenario) -> None:
    from adaptive_trip.domain.validation import validate

    loaded = scenario("rain")
    state = loaded.state.model_copy(
        update={
            "constraints": Constraints(
                required_item_ids=frozenset({"dinner"}),
                hard_budget=Money(amount="1500", currency="JPY", certainty="confirmed"),
            )
        }
    )
    candidate = Candidate(
        id="same-schedule",
        items=state.items,
        rationale="Keep the schedule.",
        signature="synthetic:park|outdoor",
    )

    report = validate(state, candidate, [], loaded.now)

    assert any(check.code == "budget" and check.status == "pass" for check in report.checks)
