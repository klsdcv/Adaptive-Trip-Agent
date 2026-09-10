from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from adaptive_trip.domain.models import Candidate, Observation, PlacesData, RouteData
from adaptive_trip.tools.contracts import ToolResult


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


def test_text_itinerary_creates_an_unconfirmed_draft(tmp_path) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.storage.repository import Repository

    with TestClient(create_app(Repository(tmp_path / "trip.db"))) as client:
        response = client.post(
            "/api/drafts",
            json={"text": "내일 미술관 갔다가 저녁", "preferences": {}},
        )

    assert response.status_code == 201
    assert response.json()["confirmed"] is False
    assert response.json()["questions"]


def test_unresolved_draft_cannot_be_confirmed(tmp_path) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.storage.repository import Repository

    with TestClient(create_app(Repository(tmp_path / "trip.db"))) as client:
        draft = client.post(
            "/api/drafts",
            json={"text": "내일 미술관 갔다가 저녁", "preferences": {}},
        ).json()
        response = client.post(
            f"/api/drafts/{draft['id']}/confirm",
            json={"confirmed_fields": {}, "request_id": "draft-1"},
        )

    assert response.status_code == 422


def test_confirmed_draft_resolves_and_persists_a_trip(tmp_path, scenario) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.storage.repository import Repository

    loaded = scenario("rain")

    class PlaceTools:
        async def call(self, request):
            return ToolResult(
                observation=Observation(
                    id="resolved-place",
                    kind="place",
                    status="ok",
                    observed_at=loaded.now,
                    valid_until=loaded.now + timedelta(hours=1),
                    source="test",
                    data=PlacesData(place_id="ChIJ-confirmed-place"),
                ),
                attempts=1,
            )

    repository = Repository(tmp_path / "trip.db")
    app = create_app(repository, tools=PlaceTools(), clock=lambda: loaded.now)
    with TestClient(app) as client:
        draft = client.post(
            "/api/drafts",
            json={"text": "오사카성 방문", "preferences": {"pace": "relaxed"}},
        ).json()
        confirmed = client.post(
            f"/api/drafts/{draft['id']}/confirm",
            json={
                "request_id": "confirm-osaka",
                "confirmed_fields": {
                    "timezone": "Asia/Tokyo",
                    "search_origin": {"latitude": 34.6937, "longitude": 135.5023},
                    "items": [{
                        "title": "오사카성",
                        "place_query": "오사카성",
                        "activity_type": "sightseeing",
                        "start": "2026-09-10T10:00:00+09:00",
                        "end": "2026-09-10T12:00:00+09:00",
                        "fixed": False,
                    }],
                },
            },
        )
        fetched = client.get(f"/api/trips/{confirmed.json()['id']}")

    assert confirmed.status_code == 201
    assert confirmed.json()["items"][0]["place_id"] == "ChIJ-confirmed-place"
    assert fetched.status_code == 200
    assert fetched.json() == confirmed.json()


def test_travel_mode_can_be_toggled_with_versioned_request(tmp_path, scenario) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.storage.repository import Repository

    loaded = scenario("rain")
    repository = Repository(tmp_path / "trip.db")
    repository.create(loaded.state)

    with TestClient(create_app(repository, clock=lambda: loaded.now)) as client:
        response = client.patch(
            f"/api/trips/{loaded.state.id}/mode",
            json={"enabled": True, "expected_version": loaded.state.version, "request_id": "mode-1"},
        )
        fetched = client.get(f"/api/trips/{loaded.state.id}")

    assert response.status_code == 200
    assert response.json()["travel_mode"] is True
    assert response.json()["version"] == loaded.state.version + 1
    assert fetched.json()["travel_mode"] is True


def test_completion_event_updates_trip_and_exposes_run_status(tmp_path, scenario) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.storage.repository import Repository

    loaded = scenario("rain")
    repository = Repository(tmp_path / "trip.db")
    repository.create(loaded.state)
    target_id = loaded.state.items[1].id

    with TestClient(create_app(repository, clock=lambda: loaded.now)) as client:
        response = client.post(
            f"/api/trips/{loaded.state.id}/events",
            json={
                "kind": "completion",
                "payload": {"item_ids": [target_id]},
                "expected_version": loaded.state.version,
                "request_id": "complete-1",
            },
        )
        run = client.get(f"/api/runs/{response.json()['run_id']}")
        fetched = client.get(f"/api/trips/{loaded.state.id}")

    assert response.status_code == 202
    assert response.json()["status"] == "completed"
    assert run.status_code == 200
    assert run.json()["status"] == "completed"
    assert fetched.json()["version"] == loaded.state.version + 1
    assert next(item for item in fetched.json()["items"] if item["id"] == target_id)["status"] == "completed"


def test_stale_user_event_is_rejected_without_changing_trip(tmp_path, scenario) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.storage.repository import Repository

    loaded = scenario("rain")
    repository = Repository(tmp_path / "trip.db")
    repository.create(loaded.state)

    with TestClient(create_app(repository, clock=lambda: loaded.now)) as client:
        first = client.patch(
            f"/api/trips/{loaded.state.id}/mode",
            json={"enabled": True, "expected_version": loaded.state.version, "request_id": "mode-1"},
        )
        stale = client.patch(
            f"/api/trips/{loaded.state.id}/mode",
            json={"enabled": False, "expected_version": loaded.state.version, "request_id": "mode-2"},
        )

    assert first.status_code == 200
    assert stale.status_code == 409


def test_duplicate_user_event_does_not_increment_trip_version_twice(tmp_path, scenario) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.storage.repository import Repository

    loaded = scenario("rain")
    repository = Repository(tmp_path / "trip.db")
    repository.create(loaded.state)
    body = {
        "kind": "weather",
        "payload": {"precipitation_probability": 80},
        "expected_version": loaded.state.version,
        "request_id": "weather-duplicate",
    }

    with TestClient(create_app(repository, clock=lambda: loaded.now)) as client:
        first = client.post(f"/api/trips/{loaded.state.id}/events", json=body)
        second = client.post(f"/api/trips/{loaded.state.id}/events", json=body)
        fetched = client.get(f"/api/trips/{loaded.state.id}")

    assert first.status_code == 202
    assert second.status_code == 202
    assert fetched.json()["version"] == loaded.state.version + 1
    assert len(repository.events(loaded.state.id)) == 1


def test_accepting_a_proposal_over_http_updates_the_trip(tmp_path, scenario) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.domain.models import Candidate, Proposal, Report
    from adaptive_trip.storage.repository import Repository

    loaded = scenario("rain")
    repository = Repository(tmp_path / "trip.db")
    repository.create(loaded.state)
    repository.save_proposal(
        Proposal(
            id="http-proposal",
            trip_id=loaded.state.id,
            base_version=loaded.state.version,
            created_at=loaded.now,
            expires_at=loaded.now + timedelta(minutes=10),
            candidates=[
                Candidate(
                    id="keep-plan",
                    items=loaded.state.items,
                    rationale="Keep itinerary.",
                    signature="keep-plan",
                )
            ],
            reports={"keep-plan": Report(checks=[])},
            status="pending",
            reason="test",
        )
    )

    with TestClient(create_app(repository, clock=lambda: loaded.now)) as client:
        response = client.post(
            f"/api/trips/{loaded.state.id}/decisions",
            json={
                "proposal_id": "http-proposal",
                "candidate_id": "keep-plan",
                "action": "accept",
                "request_id": "http-choice",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "applied"


def test_pending_proposals_can_be_loaded_after_reconnect(tmp_path, scenario) -> None:
    from adaptive_trip.api.app import create_app
    from adaptive_trip.domain.models import Proposal
    from adaptive_trip.storage.repository import Repository

    loaded = scenario("rain")
    repository = Repository(tmp_path / "trip.db")
    repository.create(loaded.state)
    repository.save_proposal(
        Proposal(
            id="pending-proposal",
            trip_id=loaded.state.id,
            base_version=loaded.state.version,
            created_at=loaded.now,
            expires_at=loaded.now + timedelta(minutes=10),
            candidates=[],
            reports={},
            status="pending",
            reason="rain",
        )
    )

    with TestClient(create_app(repository)) as client:
        response = client.get(f"/api/trips/{loaded.state.id}/proposals")

    assert response.status_code == 200
    assert [proposal["id"] for proposal in response.json()] == ["pending-proposal"]


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
