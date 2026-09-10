from __future__ import annotations

from collections.abc import Iterable

from adaptive_trip.domain.models import Check


def score(checks: Iterable[Check]) -> dict[str, float | int]:
    """Return deterministic constraint metrics for a candidate report.

    Every check contributes to the denominator: an unknown result is not silently
    dropped, so missing provider data is visible in fulfilment scores.
    """

    values = list(checks)
    total = len(values)
    passed = sum(check.status == "pass" for check in values)
    failed = sum(check.status == "fail" for check in values)
    unknown = sum(check.status == "unknown" for check in values)
    return {
        "constraint_fulfilment": passed / total if total else 0.0,
        "passed": passed,
        "failed": failed,
        "unknown": unknown,
        "total": total,
    }
