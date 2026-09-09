import json

import httpx
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize('output,reason', [('{"kind":"stop","reason":"insufficient data"}', 'insufficient data'), ('{"kind":"execute_shell","reason":"bad"}', 'invalid_model_response')])
async def test_gateway_validates_provider_output(output, reason):
    from adaptive_trip.agent.gateway import LiveModelGateway

    def respond(request):
        body = json.loads(request.content)
        assert body['model'] == 'configured-model'
        assert body['store'] is False
        assert request.headers['authorization'] == 'Bearer test-key'
        return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': output}]}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await LiveModelGateway(client, api_key='test-key', model_id='configured-model').next({})
    assert result.kind == 'stop'
    assert result.reason == reason


@pytest.mark.asyncio
async def test_gateway_maps_allowed_function_call_to_bounded_tool_request():
    from adaptive_trip.agent.gateway import LiveModelGateway

    def respond(request):
        body = json.loads(request.content)
        route_tool = next(tool for tool in body['tools'] if tool['name'] == 'route')
        assert route_tool['strict'] is True
        assert route_tool['parameters']['additionalProperties'] is False
        assert body['parallel_tool_calls'] is False
        assert body['text']['format']['type'] == 'json_schema'
        return httpx.Response(200, json={
            'id': 'resp-route',
            'status': 'completed',
            'output': [{
                'type': 'function_call',
                'call_id': 'call-route',
                'name': 'route',
                'arguments': json.dumps({
                    'origin_place_id': 'place-a',
                    'destination_place_id': 'place-b',
                    'departure_at': '2026-09-08T16:30:00+09:00',
                }),
            }],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        action = await LiveModelGateway(
            client, api_key='test-key', model_id='configured-model'
        ).next({})

    assert action.kind == 'tool'
    assert action.request is not None
    assert action.request.name == 'route'
    assert action.request.arguments['destination_place_id'] == 'place-b'
    assert action.provider_response_id == 'resp-route'
    assert action.provider_call_id == 'call-route'


@pytest.mark.asyncio
async def test_gateway_returns_tool_output_with_original_call_id():
    from adaptive_trip.agent.gateway import LiveModelGateway

    bodies = []

    def respond(request):
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:
            return httpx.Response(200, json={
                'id': 'resp-details',
                'status': 'completed',
                'output': [{
                    'type': 'function_call',
                    'call_id': 'call-details',
                    'name': 'place_details',
                    'arguments': '{"place_id":"place-a"}',
                }],
            })
        return httpx.Response(200, json={
            'id': 'resp-final',
            'status': 'completed',
            'output': [{
                'type': 'message',
                'content': [{
                    'type': 'output_text',
                    'text': '{"kind":"stop","reason":"Evidence received"}',
                }],
            }],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        gateway = LiveModelGateway(client, api_key='test-key', model_id='configured-model')
        first = await gateway.next({})
        second = await gateway.next({
            'tool_result': {
                'response_id': first.provider_response_id,
                'call_id': first.provider_call_id,
                'output': {'observation': {'status': 'ok'}},
            }
        })

    assert second.reason == 'Evidence received'
    assert bodies[1]['previous_response_id'] == 'resp-details'
    assert bodies[1]['input'][0]['type'] == 'function_call_output'
    assert bodies[1]['input'][0]['call_id'] == 'call-details'
    assert json.loads(bodies[1]['input'][0]['output'])['observation']['status'] == 'ok'


@pytest.mark.asyncio
async def test_gateway_rejects_function_names_outside_the_allowlist():
    from adaptive_trip.agent.gateway import LiveModelGateway

    def respond(request):
        return httpx.Response(200, json={
            'id': 'resp-unsafe',
            'status': 'completed',
            'output': [{
                'type': 'function_call',
                'call_id': 'call-unsafe',
                'name': 'execute_shell',
                'arguments': '{"command":"whoami"}',
            }],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        action = await LiveModelGateway(
            client, api_key='test-key', model_id='configured-model'
        ).next({})

    assert action.kind == 'stop'
    assert action.reason == 'invalid_tool_request'
