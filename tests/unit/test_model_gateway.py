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
