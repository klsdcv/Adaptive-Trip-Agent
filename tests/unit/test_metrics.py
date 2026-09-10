def test_unknown_counts_against_fulfilment() -> None:
    from adaptive_trip.domain.models import Check
    from adaptive_trip.evaluation.metrics import score

    checks = [
        Check(code="fixed", status="pass", item_id="a", evidence_ids=[], message="ok"),
        Check(code="route", status="unknown", item_id="b", evidence_ids=[], message="missing"),
    ]

    assert score(checks)["constraint_fulfilment"] == 0.5


def test_empty_checks_have_zero_fulfilment() -> None:
    from adaptive_trip.evaluation.metrics import score

    assert score([])["constraint_fulfilment"] == 0.0
