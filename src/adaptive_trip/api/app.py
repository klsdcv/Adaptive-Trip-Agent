from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI

from adaptive_trip.agent.graph import Replanner
from adaptive_trip.api.routes import build_router
from adaptive_trip.services.decisions import DecisionService
from adaptive_trip.storage.repository import Repository


def create_app(
    repository: Repository,
    *,
    decisions: DecisionService | None = None,
    replanner: Replanner | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    app = FastAPI(title="Adaptive Trip Agent")
    app.include_router(build_router(repository, decisions, replanner, clock))
    return app
