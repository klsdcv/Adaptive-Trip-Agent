def test_default_scenarios_are_named_and_serializable() -> None:
    from adaptive_trip.evaluation.scenarios import default_scenarios

    scenarios = default_scenarios()
    assert {scenario["name"] for scenario in scenarios} >= {"rain", "delay", "closed"}
