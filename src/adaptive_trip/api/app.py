from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import FastAPI

from adaptive_trip.agent.graph import Replanner
from adaptive_trip.api.routes import build_router
from adaptive_trip.services.decisions import DecisionService
from adaptive_trip.services.intake import IntakeParser, IntakeService
from adaptive_trip.storage.repository import Repository
from adaptive_trip.tools.contracts import ToolProvider


def create_app(
    repository: Repository,
    *,
    decisions: DecisionService | None = None,
    replanner: Replanner | None = None,
    clock: Callable[[], datetime] | None = None,
    intake: IntakeService | None = None,
    tools: ToolProvider | None = None,
    intake_parser: IntakeParser | None = None,
) -> FastAPI:
    active_clock = clock or (lambda: datetime.now(timezone.utc))
    active_decisions = decisions or DecisionService(repository, clock=active_clock)
    active_intake = intake or IntakeService(
        tools=tools,
        clock=active_clock,
        repository=repository,
        parser=intake_parser,
    )
    app = FastAPI(title="Adaptive Trip Agent")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(
        build_router(repository, active_decisions, replanner, active_clock, active_intake)
    )
    return app
