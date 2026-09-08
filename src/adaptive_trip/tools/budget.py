from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CallBudget:
    max_requests: int
    used: int = 0

    def reserve(self, units: int) -> bool:
        if units < 1:
            raise ValueError("units must be positive")
        if self.used + units > self.max_requests:
            return False
        self.used += units
        return True
