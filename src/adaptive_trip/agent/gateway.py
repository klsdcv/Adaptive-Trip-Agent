from __future__ import annotations

import json
from typing import Literal

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from adaptive_trip.agent.contracts import AgentAction
from adaptive_trip.agent.prompts import REPLANNING_INSTRUCTIONS
from adaptive_trip.domain.models import Candidate
from adaptive_trip.tools.contracts import ToolRequest


class _StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _PlaceSearchArguments(_StrictArguments):
    query: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class _PlaceDetailsArguments(_StrictArguments):
    place_id: str


class _RouteArguments(_StrictArguments):
    origin_place_id: str
    destination_place_id: str
    departure_at: AwareDatetime


class _WeatherArguments(_StrictArguments):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    forecast_at: AwareDatetime


class _ModelDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["candidates", "stop"]
    candidates: list[Candidate] = Field(default_factory=list)
    reason: str


_ARGUMENT_MODELS = {
    "places_search": _PlaceSearchArguments,
    "place_details": _PlaceDetailsArguments,
    "route": _RouteArguments,
    "weather": _WeatherArguments,
}

_TOOL_METADATA = {
    "places_search": (
        "Search for one relevant place near coordinates.",
        "places_text_search",
    ),
    "place_details": (
        "Get coordinates and opening data for a place ID.",
        "places_details",
    ),
    "route": (
        "Get travel duration between two place IDs for a departure time.",
        "routes_essentials",
    ),
    "weather": (
        "Get precipitation probability at coordinates and time.",
        "weather",
    ),
}


def _tool_definitions() -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "name": name,
            "description": _TOOL_METADATA[name][0],
            "parameters": model.model_json_schema(),
            "strict": True,
        }
        for name, model in _ARGUMENT_MODELS.items()
    ]


class LiveModelGateway:
    """Bounded Responses API decision call; this class never executes tools."""

    def __init__(self, client: httpx.AsyncClient, *, api_key: str, model_id: str):
        if not api_key.strip() or not model_id.strip():
            raise ValueError("OpenAI credentials and model ID are required")
        self._client = client
        self._key = api_key
        self._model = model_id

    async def next(self, context: dict[str, object]) -> AgentAction:
        request_body = self._request_body(context)
        if request_body is None:
            return AgentAction(kind="stop", reason="invalid_tool_result")
        try:
            response = await self._client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self._key}"},
                json=request_body,
                timeout=60,
            )
            if response.status_code != 200:
                return AgentAction(
                    kind="stop", reason=f"model_http_{response.status_code}"
                )
            payload = response.json()
            if payload.get("status") != "completed":
                return AgentAction(kind="stop", reason="model_incomplete")
            function_calls = [
                item
                for item in payload.get("output", [])
                if item.get("type") == "function_call"
            ]
            if function_calls:
                if len(function_calls) != 1:
                    return AgentAction(kind="stop", reason="invalid_tool_request")
                return self._tool_action(
                    payload, function_calls[0], request_body["input"]
                )
            output = "".join(
                part["text"]
                for item in payload.get("output", [])
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            decision = _ModelDecision.model_validate_json(output)
            return AgentAction(
                kind=decision.kind,
                candidates=decision.candidates,
                reason=decision.reason,
            )
        except httpx.RequestError:
            return AgentAction(kind="stop", reason="model_connection_error")
        except (ValueError, TypeError, KeyError, AttributeError):
            return AgentAction(kind="stop", reason="invalid_model_response")

    def _request_body(self, context: dict[str, object]) -> dict[str, object] | None:
        body: dict[str, object] = {
            "model": self._model,
            "store": False,
            "max_output_tokens": 6000,
            "instructions": REPLANNING_INSTRUCTIONS,
            "tools": _tool_definitions(),
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "agent_action",
                    "schema": _ModelDecision.model_json_schema(),
                    "strict": False,
                }
            },
        }
        tool_result = context.get("tool_result")
        if tool_result is None:
            body["input"] = [
                {
                    "role": "user",
                    "content": json.dumps(context, ensure_ascii=False),
                }
            ]
            return body
        if not isinstance(tool_result, dict):
            return None
        response_output = tool_result.get("response_output")
        call_id = tool_result.get("call_id")
        if (
            not isinstance(response_output, list)
            or not all(isinstance(item, dict) for item in response_output)
            or not isinstance(call_id, str)
        ):
            return None
        body["input"] = [
            *response_output,
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(tool_result.get("output"), ensure_ascii=False),
            }
        ]
        return body

    @staticmethod
    def _tool_action(
        payload: dict[str, object],
        function_call: dict[str, object],
        provider_input: object,
    ) -> AgentAction:
        name = function_call.get("name")
        if name not in _ARGUMENT_MODELS:
            return AgentAction(kind="stop", reason="invalid_tool_request")
        try:
            raw_arguments = json.loads(function_call["arguments"])
            arguments = _ARGUMENT_MODELS[name].model_validate(raw_arguments).model_dump(
                mode="json"
            )
            response_id = payload["id"]
            call_id = function_call["call_id"]
            response_output = payload["output"]
            if (
                not isinstance(response_id, str)
                or not isinstance(call_id, str)
                or not isinstance(provider_input, list)
                or not all(isinstance(item, dict) for item in provider_input)
                or not isinstance(response_output, list)
                or not all(isinstance(item, dict) for item in response_output)
            ):
                raise ValueError("missing provider identifiers")
            return AgentAction(
                kind="tool",
                request=ToolRequest(
                    name=name,
                    arguments=arguments,
                    sku=_TOOL_METADATA[name][1],
                    units=1,
                ),
                reason=f"Model requested {name} evidence.",
                provider_response_id=response_id,
                provider_call_id=call_id,
                provider_output=[*provider_input, *response_output],
            )
        except (json.JSONDecodeError, ValidationError, TypeError, KeyError, ValueError):
            return AgentAction(kind="stop", reason="invalid_tool_request")


class ScriptedGateway:
    """Deterministic model replacement used by synthetic tests and demos."""

    def __init__(self, actions: list[AgentAction]) -> None:
        self._actions = iter(actions)

    async def next(self, context: dict[str, object]) -> AgentAction:
        del context
        return next(
            self._actions,
            AgentAction(kind="stop", reason="No scripted action remains."),
        )
