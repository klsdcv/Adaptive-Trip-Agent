from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from adaptive_trip.agent.contracts import AgentAction, ModelGateway
from adaptive_trip.domain.models import (
    ChangeEvent,
    Observation,
    Proposal,
    Report,
    RunResult,
    TripState,
)
from adaptive_trip.domain.validation import validate
from adaptive_trip.tools.budget import CallBudget
from adaptive_trip.tools.contracts import ToolProvider


class Replanner:
    def __init__(
        self,
        model: ModelGateway,
        tools: ToolProvider,
        *,
        target_candidates: int = 3,
        max_tool_calls: int = 18,
        max_model_calls: int = 6,
        max_rounds: int = 3,
        max_candidates: int = 9,
    ) -> None:
        self._model = model
        self._tools = tools
        self._target_candidates = target_candidates
        self._max_tool_calls = max_tool_calls
        self._max_model_calls = max_model_calls
        self._max_rounds = max_rounds
        self._max_candidates = max_candidates

    async def run(
        self,
        state: TripState,
        event: ChangeEvent,
        observations: list[Observation],
        now: datetime,
    ) -> RunResult:
        workflow = StateGraph(dict)
        budget = CallBudget(max_requests=self._max_tool_calls)

        async def decide(graph_state: dict[str, object]) -> dict[str, object]:
            model_calls = int(graph_state["model_calls"])
            trace = list(graph_state["trace"])
            if model_calls >= self._max_model_calls:
                action = AgentAction(kind="stop", reason="model_call_limit_reached")
            elif graph_state.get("budget_exhausted"):
                action = AgentAction(kind="stop", reason="tool_call_limit_reached")
            else:
                context = dict(graph_state["context"])
                context["observations"] = [
                    observation.model_dump(mode="json")
                    for observation in graph_state["observations"]
                ]
                if graph_state.get("tool_result") is not None:
                    context["tool_result"] = graph_state["tool_result"]
                if graph_state.get("validation"):
                    context["validation"] = graph_state["validation"]
                action = await self._model.next(context)
                model_calls += 1
            trace.append({"node": "decide", "action": action.kind})
            return {
                **graph_state,
                "action": action,
                "model_calls": model_calls,
                "reason": action.reason,
                "trace": trace,
            }

        async def call_tool(graph_state: dict[str, object]) -> dict[str, object]:
            action = graph_state["action"]
            trace = list(graph_state["trace"])
            if not isinstance(action, AgentAction) or action.request is None:
                return {**graph_state, "budget_exhausted": True, "trace": trace}
            if not budget.reserve(action.request.units):
                trace.append({"node": "call_tool", "status": "limit_reached"})
                return {**graph_state, "budget_exhausted": True, "trace": trace}
            result = await self._tools.call(action.request)
            observations = [*graph_state["observations"], result.observation]
            trace.append(
                {
                    "node": "call_tool",
                    "name": action.request.name,
                    "status": result.observation.status,
                }
            )
            return {
                **graph_state,
                "observations": observations,
                "tool_calls": budget.used,
                "tool_result": {
                    "response_output": action.provider_output,
                    "call_id": action.provider_call_id,
                    "output": result.model_dump(mode="json"),
                },
                "trace": trace,
            }

        def check_candidates(graph_state: dict[str, object]) -> dict[str, object]:
            action = graph_state["action"]
            if isinstance(action, AgentAction) and action.kind == 'stop':
                return {
                    **graph_state,
                    "eligible": [],
                    "reports": {},
                    "reason": action.reason,
                }
            if not isinstance(action, AgentAction) or action.kind != "candidates":
                return {
                    **graph_state,
                    "eligible": [],
                    "reports": {},
                    "reason": "No candidate action was produced.",
                }
            reports = dict(graph_state["reports"])
            eligible = list(graph_state["eligible"])
            seen_signatures = set(graph_state["seen_signatures"])
            candidate_count = int(graph_state["candidate_count"])
            current_reports: list[Report] = []
            for candidate in action.candidates:
                if candidate_count >= self._max_candidates:
                    break
                candidate_count += 1
                if candidate.signature in seen_signatures:
                    continue
                seen_signatures.add(candidate.signature)
                report = validate(state, candidate, graph_state["observations"], now)
                reports[candidate.id] = report
                current_reports.append(report)
                if report.eligible and len(eligible) < self._target_candidates:
                    eligible.append(candidate)
            trace = [
                *graph_state["trace"],
                {"node": "validate", "eligible": len(eligible)},
            ]
            return {
                **graph_state,
                "eligible": eligible,
                "reports": reports,
                "reason": action.reason,
                "rounds": int(graph_state["rounds"]) + 1,
                "candidate_count": candidate_count,
                "seen_signatures": list(seen_signatures),
                "validation": [
                    check.model_dump(mode="json")
                    for report in current_reports
                    for check in report.checks
                ],
                "tool_result": None,
                "trace": trace,
            }

        def route_action(graph_state: dict[str, object]):
            action = graph_state["action"]
            if isinstance(action, AgentAction) and action.kind == "tool":
                return "call_tool"
            if isinstance(action, AgentAction) and action.kind == "candidates":
                return "validate"
            return "finish"

        def route_validation(graph_state: dict[str, object]):
            if len(graph_state["eligible"]) >= self._target_candidates:
                return "finish"
            if int(graph_state["rounds"]) >= self._max_rounds:
                return "finish"
            if int(graph_state["candidate_count"]) >= self._max_candidates:
                return "finish"
            if int(graph_state["model_calls"]) >= self._max_model_calls:
                return "finish"
            return "decide"

        workflow.add_node("decide", decide)
        workflow.add_node("call_tool", call_tool)
        workflow.add_node("validate", check_candidates)
        workflow.add_edge(START, "decide")
        workflow.add_conditional_edges(
            "decide",
            route_action,
            {"call_tool": "call_tool", "validate": "validate", "finish": END},
        )
        workflow.add_edge("call_tool", "decide")
        workflow.add_conditional_edges(
            "validate",
            route_validation,
            {"decide": "decide", "finish": END},
        )
        result = await workflow.compile().ainvoke(
            {
                "context": {
                    "trip": state.model_dump(mode="json"),
                    "event": event.model_dump(mode="json"),
                    "observations": [observation.model_dump(mode="json") for observation in observations],
                },
                "observations": list(observations),
                "model_calls": 0,
                "tool_calls": 0,
                "eligible": [],
                "reports": {},
                "reason": "No candidate action was produced.",
                "rounds": 0,
                "candidate_count": 0,
                "seen_signatures": [],
                "validation": [],
                "trace": [],
            }
        )

        eligible = result["eligible"]
        reports = result["reports"]
        proposal = Proposal(
            id=str(uuid4()),
            trip_id=state.id,
            base_version=state.version,
            created_at=now,
            expires_at=now + timedelta(minutes=10),
            candidates=eligible,
            reports={candidate.id: reports[candidate.id] for candidate in eligible},
            status="pending",
            reason=result["reason"],
        )
        return RunResult(
            proposal=proposal,
            observations=result["observations"],
            checks=[check for report in reports.values() for check in report.checks],
            trace=result["trace"],
            tool_calls=result["tool_calls"],
            model_calls=result["model_calls"],
            stop_reason=("target_reached" if len(eligible) >= self._target_candidates else "insufficient_valid_candidates"),
        )
