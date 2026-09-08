from __future__ import annotations

from adaptive_trip.agent.contracts import AgentAction


class ScriptedGateway:
    """Deterministic model replacement used by synthetic tests and demos."""

    def __init__(self, actions: list[AgentAction]) -> None:
        self._actions = iter(actions)

    async def next(self, context: dict[str, object]) -> AgentAction:
        del context
        return next(
            self._actions,
            AgentAction(kind="stop", reason="No scripted action remains."),
        )
