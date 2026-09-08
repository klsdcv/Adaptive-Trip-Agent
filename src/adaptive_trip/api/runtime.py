"""Local server entrypoint: uvicorn adaptive_trip.api.runtime:build_app --factory."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import os

import httpx
from dotenv import dotenv_values
from fastapi import HTTPException

from adaptive_trip.agent.gateway import LiveModelGateway, ScriptedGateway
from adaptive_trip.agent.graph import Replanner
from adaptive_trip.api.app import create_app
from adaptive_trip.storage.repository import Repository
from adaptive_trip.tools.contracts import ToolProvider, ToolRequest, ToolResult
from adaptive_trip.tools.google_places import GoogleTools
from adaptive_trip.tools.open_meteo import OpenMeteoTools
from adaptive_trip.tools.synthetic import SyntheticTools


class LiveTools(ToolProvider):
    def __init__(self, client, key, clock):
        self.weather = OpenMeteoTools(client, clock=clock)
        self.google = GoogleTools(client, api_key=key, clock=clock)

    async def call(self, request):
        provider = self.weather if request.name == 'weather' else self.google
        return await provider.call(request)


def build_app(*, settings=None, transport=None, clock=None):
    configuration = settings if settings is not None else {**dotenv_values(Path('.env')), **os.environ}
    mode = configuration.get('APP_MODE', 'synthetic')
    if mode not in {'synthetic', 'live'}:
        raise ValueError('APP_MODE must be synthetic or live')
    active_clock = clock or (lambda: datetime.now(timezone.utc))
    client = httpx.AsyncClient(transport=transport, timeout=8)
    if mode == 'live':
        for name in ('OPENAI_API_KEY', 'OPENAI_MODEL', 'GOOGLE_MAPS_API_KEY'):
            if not configuration.get(name):
                raise ValueError(f'{name} is required in live mode')
        tools = LiveTools(client, configuration['GOOGLE_MAPS_API_KEY'], active_clock)
        model = LiveModelGateway(client, api_key=configuration['OPENAI_API_KEY'], model_id=configuration['OPENAI_MODEL'])
    else:
        tools = SyntheticTools([])
        model = ScriptedGateway([])
    repository = Repository(Path(configuration.get('APP_DATA_DIR', '.local')) / 'trip.db')
    app = create_app(repository, replanner=Replanner(model, tools), clock=active_clock)

    @asynccontextmanager
    async def lifespan(app):
        async with client:
            yield

    app.router.lifespan_context = lifespan

    @app.get('/api/trips/{trip_id}/weather', response_model=ToolResult)
    async def weather(trip_id: str):
        try:
            trip = repository.get(trip_id)
        except KeyError:
            raise HTTPException(404, 'Trip not found.') from None
        if trip.position is None:
            raise HTTPException(422, 'A current position is required.')
        try:
            return await tools.call(ToolRequest(name='weather', arguments={
                'latitude': trip.position.latitude, 'longitude': trip.position.longitude,
            }, sku='weather', units=1))
        except (httpx.RequestError, ValueError):
            raise HTTPException(502, 'Weather provider unavailable.') from None

    return app
