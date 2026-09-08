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
