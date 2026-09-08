from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from adaptive_trip.domain.models import Candidate, Observation, PlacesData, RouteData


def test_create_and_get_trip_over_http(tmp_path, scenario) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.storage.repository import Repository

    loaded = scenario("rain")
    app = create_app(Repository(tmp_path / "trip.db"))

    with TestClient(app) as client:
        created = client.post("/api/trips", json=loaded.state.model_dump(mode="json"))
        fetched = client.get(f"/api/trips/{loaded.state.id}")

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json()["version"] == loaded.state.version


def test_unknown_trip_returns_not_found(tmp_path) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.storage.repository import Repository

    with TestClient(create_app(Repository(tmp_path / "trip.db"))) as client:
        response = client.get("/api/trips/missing")

    assert response.status_code == 404


def test_event_creates_a_pending_replanning_proposal(tmp_path, scenario) -> None:
    from adaptive_trip.agent.contracts import AgentAction
    from adaptive_trip.agent.gateway import ScriptedGateway
    from adaptive_trip.agent.graph import Replanner
    from adaptive_trip.api.app import create_app
    from adaptive_trip.storage.repository import Repository
    from adaptive_trip.tools.synthetic import SyntheticTools

    loaded = scenario("rain")
    candidate = Candidate(
        id="museum-plan",
        items=loaded.state.items,
        rationale="Test proposal.",
        signature="museum-plan",
    )
    # The candidate is intentionally not valid; this endpoint test verifies persistence,
    # while candidate validity is covered by unit-level graph tests.
    replanner = Replanner(
        ScriptedGateway([AgentAction(kind="candidates", candidates=[candidate], reason="test")]),
        SyntheticTools([]),
    )
    repository = Repository(tmp_path / "trip.db")
    app = create_app(repository, replanner=replanner, clock=lambda: loaded.now)

    with TestClient(app) as client:
        client.post("/api/trips", json=loaded.state.model_dump(mode="json"))
        response = client.post(
            f"/api/trips/{loaded.state.id}/events",
            json={
                "event": loaded.event.model_dump(mode="json"),
                "observations": [],
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
