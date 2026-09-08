from __future__ import annotations

import pytest


def test_budget_counts_physical_requests() -> None:
    from adaptive_trip.tools.budget import CallBudget

    budget = CallBudget(max_requests=2)

    assert budget.reserve(1)
    assert budget.reserve(1)
    assert not budget.reserve(1)
    assert budget.used == 2


def test_budget_rejects_non_positive_units() -> None:
    from adaptive_trip.tools.budget import CallBudget

    with pytest.raises(ValueError):
        CallBudget(max_requests=2).reserve(0)
