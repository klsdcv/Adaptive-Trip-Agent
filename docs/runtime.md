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
For the browser UI, start a second terminal in `web`, run `npm run dev`, and
open the local URL printed by Vite. Its development proxy forwards `/api` to
the backend on `127.0.0.1:8000`.

In live mode, the intake flow uses a stateless OpenAI structured-output request
to extract multiple places, local times, fixed reservations, questions, and
explicit assumptions from free text. Review those fields before confirming.
`POST /api/drafts/{draft_id}/confirm` resolves each query through Google Places
and persists only the resulting provider place ID in the confirmed trip. The
first resolved place supplies the destination coordinates when the optional
search coordinates are blank. Local form times are interpreted in the selected
trip timezone. Drafts and idempotent confirmation request IDs persist in SQLite.

`GET /api/trips/{id}/weather` fetches Open-Meteo for its current position.
`GET /api/trips/{id}/notifications` returns detected weather impacts.
`PATCH /api/trips/{id}/mode` toggles travel mode with an expected state version.
User status changes use `POST /api/trips/{id}/events` with `kind`, `payload`,
`expected_version`, and `request_id`; the response is a `run_id` that can be
polled at `GET /api/runs/{id}`. Completion, position, preference, expense,
fixed-condition, delay, closure, weather, and fatigue events are versioned and
deduplicated by request ID.
`POST /api/trips/{id}/events` invokes the configured OpenAI model and validates
its candidates. Provider errors and invalid model output preserve the itinerary.
The model can request bounded Google place searches, place details, and routes,
or Open-Meteo weather observations. Tool results are returned to the model
without storing OpenAI Responses, and every candidate is checked by deterministic
domain validation before it appears as a proposal.
Travel-mode trips are checked once at server startup when due and then on the
configured interval. The next due time is persisted across server restarts.

Current limitations: ambiguous or missing dates and times still require user
review before confirmation. Every item that participates in route and
opening-hours validation must have a real Google place ID; the confirmation
flow resolves that ID.
The weather endpoint is separate from manual event submission. An empty proposal
means no validated candidates, not a successful end-to-end travel plan.
Synthetic mode has no scripted demo actions in this entrypoint. Use existing
test fixtures for reproducible scenarios.

OpenAI final decisions use JSON Schema structured output plus local Pydantic
validation. Function arguments use strict schemas and an allowlist; malformed
model decisions may retry only within the configured model-call limit.

Weather data: [Open-Meteo](https://open-meteo.com/), used under its applicable
terms; this runtime is intended for local non-commercial development.
