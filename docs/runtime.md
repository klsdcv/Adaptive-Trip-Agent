# Local runtime

Run from the implementation checkout, where `.env` and `pyproject.toml` live:

```sh
python -m uvicorn adaptive_trip.api.runtime:build_app --factory --host 127.0.0.1 --port 8000
```

Use the project virtual environment's Python. On Windows this is
`.venv\Scripts\python.exe`; on macOS it is `.venv/bin/python`.

`APP_MODE=live` requires `OPENAI_API_KEY`, `OPENAI_MODEL`, and
`GOOGLE_MAPS_API_KEY`. `APP_DATA_DIR` defaults to `.local` and
`MONITOR_INTERVAL_SECONDS` defaults to `1800` (30 minutes).
The default mode is synthetic. Keys remain on the server.

Open `/docs` for the interactive API. Create a trip using `POST /api/trips`.
`GET /api/trips/{id}/weather` fetches Open-Meteo for its current position.
`GET /api/trips/{id}/notifications` returns detected weather impacts.
`POST /api/trips/{id}/events` invokes the configured OpenAI model and validates
its candidates. Provider errors and invalid model output preserve the itinerary.
Travel-mode trips are checked once at server startup when due and then on the
configured interval. The next due time is persisted across server restarts.

Current limitations: the graph does not yet fetch missing place/route evidence automatically.
The weather endpoint is separate from event submission. The UI still needs
weather controls. An empty proposal means no validated candidates, not a
successful end-to-end travel plan. Synthetic mode has no scripted demo actions
in this entrypoint. Use existing test fixtures for reproducible scenarios.

OpenAI responses use JSON mode plus local Pydantic validation; strict structured
outputs and model-driven tool selection remain follow-up work.

Weather data: [Open-Meteo](https://open-meteo.com/), used under its applicable
terms; this runtime is intended for local non-commercial development.
