from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import random
from collections.abc import Awaitable, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from adaptive_trip.domain.models import Check

from .metrics import score

Strategy = Callable[[Any, int], Iterable[Check] | Awaitable[Iterable[Check]]]


async def evaluate(
    scenarios: Iterable[Any],
    strategies: Mapping[str, Strategy],
    repetitions: int = 1,
    seed: int = 0,
) -> dict[str, Any]:
    """Run strategies against scenarios and return mean numeric metrics."""
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    scenario_list = list(scenarios)
    totals = {name: {} for name in strategies}
    counts = {name: 0 for name in strategies}
    rng = random.Random(seed)
    for _ in range(repetitions):
        for scenario in scenario_list:
            run_seed = rng.randrange(2**32)
            for name, strategy in strategies.items():
                result = strategy(scenario, run_seed)
                checks = await result if inspect.isawaitable(result) else result
                metrics = score(checks)
                counts[name] += 1
                for key, value in metrics.items():
                    if isinstance(value, (int, float)):
                        totals[name][key] = totals[name].get(key, 0.0) + value
    return {
        "seed": seed,
        "repetitions": repetitions,
        "scenario_count": len(scenario_list),
        "strategies": {
            name: {key: value / counts[name] for key, value in metrics.items()}
            for name, metrics in totals.items()
        },
    }


def write_results(path: str | Path, result: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run synthetic trip evaluations")
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    scenarios = json.loads(args.scenarios.read_text(encoding="utf-8"))

    async def baseline(_scenario: Any, _seed: int) -> list[Check]:
        return []

    result = asyncio.run(evaluate(scenarios, {"baseline": baseline}, args.repetitions, args.seed))
    write_results(args.output, result)


if __name__ == "__main__":
    _main()
