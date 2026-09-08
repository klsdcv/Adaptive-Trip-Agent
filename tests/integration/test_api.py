from __future__ import annotations

from fastapi.testclient import TestClient


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
