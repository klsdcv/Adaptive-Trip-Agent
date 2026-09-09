import json

import httpx
from fastapi.testclient import TestClient


def test_live_runtime_routes_weather_and_events(tmp_path, scenario):
    from adaptive_trip.api.runtime import build_app

    loaded = scenario('rain')
    hosts = []

    def respond(request):
        hosts.append(request.url.host)
        if request.url.host == 'api.open-meteo.com':
            return httpx.Response(200, json={'hourly': {'time': ['2026-09-08T05:00'], 'precipitation_probability': [70]}})
        return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps({'kind': 'stop', 'reason': 'Need verified routes'})}]}]})

    app = build_app(settings={'APP_MODE': 'live', 'APP_DATA_DIR': str(tmp_path), 'OPENAI_API_KEY': 'test', 'OPENAI_MODEL': 'test', 'GOOGLE_MAPS_API_KEY': 'test'}, transport=httpx.MockTransport(respond), clock=lambda: loaded.now)
    with TestClient(app) as client:
        assert client.post('/api/trips', json=loaded.state.model_dump(mode='json')).status_code == 201
        weather = client.get(f'/api/trips/{loaded.state.id}/weather')
        assert weather.status_code == 200
        assert weather.json()['observation']['source'] == 'open_meteo'
        response = client.post(f'/api/trips/{loaded.state.id}/events', json={'event': loaded.event.model_dump(mode='json'), 'observations': []})
        assert response.status_code == 202
        assert response.json()['reason'] == 'Need verified routes'
    assert 'api.open-meteo.com' in hosts
    assert 'api.openai.com' in hosts


def test_live_runtime_monitors_due_trips_and_exposes_notifications(tmp_path, scenario):
    from adaptive_trip.api.runtime import build_app
    from adaptive_trip.storage.repository import Repository

    loaded = scenario('rain')
    data_dir = tmp_path / 'runtime-data'
    repository = Repository(data_dir / 'trip.db')
    repository.create(loaded.state)
    weather_requests = 0

    def respond(request):
        nonlocal weather_requests
        if request.url.host == 'api.open-meteo.com':
            weather_requests += 1
            return httpx.Response(200, json={
                'hourly': {
                    'time': ['2026-09-08T05:00'],
                    'precipitation_probability': [80],
                }
            })
        return httpx.Response(200, json={
            'status': 'completed',
            'output': [{
                'type': 'message',
                'content': [{
                    'type': 'output_text',
                    'text': json.dumps({'kind': 'stop', 'reason': 'Need verified routes'}),
                }],
            }],
        })

    settings = {
        'APP_MODE': 'live',
        'APP_DATA_DIR': str(data_dir),
        'OPENAI_API_KEY': 'test',
        'OPENAI_MODEL': 'test',
        'GOOGLE_MAPS_API_KEY': 'test',
        'MONITOR_INTERVAL_SECONDS': '1800',
    }
    first_app = build_app(
        settings=settings,
        transport=httpx.MockTransport(respond),
        clock=lambda: loaded.now,
    )
    with TestClient(first_app) as client:
        response = client.get(f'/api/trips/{loaded.state.id}/notifications')

    assert response.status_code == 200
    assert [event['kind'] for event in response.json()] == ['weather']
    assert weather_requests == 1

    second_app = build_app(
        settings=settings,
        transport=httpx.MockTransport(respond),
        clock=lambda: loaded.now,
    )
    with TestClient(second_app):
        pass

    assert weather_requests == 1


def test_live_runtime_structures_free_text_into_multiple_draft_items(tmp_path, scenario):
    from adaptive_trip.api.runtime import build_app

    loaded = scenario("rain")

    def respond(request):
        parsed = {
            "items": [
                {
                    "id": "item-1", "title": "오사카성", "place_query": "오사카성",
                    "activity_type": "sightseeing", "start": "2026-09-10T10:00:00",
                    "end": "2026-09-10T12:00:00", "fixed": False,
                    "rain_sensitive": True,
                },
                {
                    "id": "item-2", "title": "도톤보리 저녁",
                    "place_query": "도톤보리 오사카", "activity_type": "dinner",
                    "start": "2026-09-10T19:00:00", "end": "2026-09-10T20:30:00",
                    "fixed": True, "rain_sensitive": False,
                },
            ],
            "questions": [],
            "assumptions": [],
        }
        return httpx.Response(200, json={
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(parsed)}],
            }],
        })

    app = build_app(
        settings={
            "APP_MODE": "live",
            "APP_DATA_DIR": str(tmp_path),
            "OPENAI_API_KEY": "test",
            "OPENAI_MODEL": "test",
            "GOOGLE_MAPS_API_KEY": "test",
        },
        transport=httpx.MockTransport(respond),
        clock=lambda: loaded.now,
    )
    with TestClient(app) as client:
        response = client.post("/api/drafts", json={
            "text": "오사카성과 도톤보리 저녁 예약",
            "preferences": {"timezone": "Asia/Tokyo"},
        })

    assert response.status_code == 201
    assert [item["title"] for item in response.json()["items"]] == [
        "오사카성", "도톤보리 저녁",
    ]
