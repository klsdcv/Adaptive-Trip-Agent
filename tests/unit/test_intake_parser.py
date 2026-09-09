from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest


@pytest.mark.asyncio
async def test_live_intake_parser_uses_stateless_structured_output() -> None:
    from adaptive_trip.services.intake_openai import LiveIntakeParser

    captured = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        parsed = {
            "items": [
                {
                    "id": "item-1",
                    "title": "오사카성",
                    "place_query": "오사카성",
                    "activity_type": "sightseeing",
                    "start": "2026-09-10T10:00:00",
                    "end": "2026-09-10T12:00:00",
                    "fixed": False,
                    "rain_sensitive": True,
                },
                {
                    "id": "item-2",
                    "title": "도톤보리 저녁",
                    "place_query": "도톤보리 오사카",
                    "activity_type": "dinner",
                    "start": "2026-09-10T19:00:00",
                    "end": "2026-09-10T20:30:00",
                    "fixed": True,
                    "rain_sensitive": False,
                },
            ],
            "questions": [],
            "assumptions": ["저녁 체류시간을 90분으로 추정했습니다."],
        }
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(parsed)}],
                }],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await LiveIntakeParser(
            client,
            api_key="test-key",
            model_id="test-model",
        ).parse(
            "9월 10일 10시 오사카성, 19시 도톤보리 저녁 예약",
            {"pace": "relaxed"},
            datetime(2026, 9, 9, tzinfo=timezone.utc),
        )

    assert [item.title for item in result.items] == ["오사카성", "도톤보리 저녁"]
    assert result.items[0].start == "2026-09-10T10:00:00"
    assert captured["model"] == "test-model"
    assert captured["store"] is False
    assert captured["text"]["format"]["type"] == "json_schema"
    assert "2026-09-09T00:00:00+00:00" in captured["input"]


@pytest.mark.asyncio
async def test_live_intake_parser_rejects_malformed_provider_output() -> None:
    from adaptive_trip.services.intake_openai import IntakeParserError, LiveIntakeParser

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{
                    "type": "message",
                    "content": [{"type": "output_text", "text": "not-json"}],
                }],
            },
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        parser = LiveIntakeParser(client, api_key="test-key", model_id="test-model")
        with pytest.raises(IntakeParserError, match="invalid"):
            await parser.parse("오사카성", {}, datetime.now(timezone.utc))
