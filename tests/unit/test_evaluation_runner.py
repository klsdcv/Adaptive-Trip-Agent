import json

import pytest


@pytest.mark.asyncio
async def test_evaluate_averages_strategy_scores() -> None:
    from adaptive_trip.domain.models import Check
    from adaptive_trip.evaluation.runner import evaluate

    scenarios = [{"name": "rain"}, {"name": "delay"}]

    async def always_pass(_scenario, _seed):
        return [Check(code="fixed", status="pass", message="ok")]

    result = await evaluate(scenarios, {"agent": always_pass}, repetitions=2, seed=7)

    assert result["repetitions"] == 2
    assert result["strategies"]["agent"]["constraint_fulfilment"] == 1.0


def test_write_results(tmp_path) -> None:
    from adaptive_trip.evaluation.runner import write_results

    target = tmp_path / "nested" / "results.json"
    write_results(target, {"ok": True})
    assert json.loads(target.read_text()) == {"ok": True}
