from fastapi.testclient import TestClient


def test_health_endpoint_reports_service(tmp_path) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.storage.repository import Repository

    with TestClient(create_app(Repository(tmp_path / "trip.db"))) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
