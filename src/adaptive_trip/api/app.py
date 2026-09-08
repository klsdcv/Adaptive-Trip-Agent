from __future__ import annotations

from fastapi import FastAPI

from adaptive_trip.api.routes import build_router
from adaptive_trip.storage.repository import Repository


def create_app(repository: Repository) -> FastAPI:
    app = FastAPI(title="Adaptive Trip Agent")
    app.include_router(build_router(repository))
    return app
