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
