"""Offline evaluation helpers for synthetic itinerary scenarios."""

from .metrics import score
from .scenarios import default_scenarios

__all__ = ["default_scenarios", "score"]
