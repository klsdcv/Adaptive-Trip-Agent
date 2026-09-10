from __future__ import annotations

from typing import Any


def default_scenarios() -> list[dict[str, Any]]:
    """Small, provider-free scenarios used for smoke evaluations and demos."""
    return [
        {"name": "rain", "event": "weather", "severity": "high"},
        {"name": "delay", "event": "delay", "minutes": 30},
        {"name": "closed", "event": "closed"},
    ]
