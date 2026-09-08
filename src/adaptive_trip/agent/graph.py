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
from adaptive_trip.tools.contracts import ToolProvider


class Replanner:
    def __init__(self, model: ModelGateway, tools: ToolProvider, *, target_candidates: int = 3) -> None:
        self._model = model
        self._tools = tools
        self._target_candidates = target_candidates

    async def run(
        self,
        state: TripState,
        event: ChangeEvent,
        observations: list[Observation],
        now: datetime,
    ) -> RunResult:
        workflow = StateGraph(dict)

        async def decide(graph_state: dict[str, object]) -> dict[str, object]:
            action = await self._model.next(graph_state["context"])
            return {"action": action}

        def check_candidates(graph_state: dict[str, object]) -> dict[str, object]:
            action = graph_state["action"]
            if not isinstance(action, AgentAction) or action.kind != "candidates":
                return {"eligible": [], "reports": {}, "reason": "No candidate action was produced."}
            reports: dict[str, Report] = {}
            eligible = []
            seen_signatures: set[str] = set()
            for candidate in action.candidates:
                if candidate.signature in seen_signatures:
                    continue
                seen_signatures.add(candidate.signature)
                report = validate(state, candidate, observations, now)
                reports[candidate.id] = report
                if report.eligible and len(eligible) < self._target_candidates:
                    eligible.append(candidate)
            return {"eligible": eligible, "reports": reports, "reason": action.reason}

        workflow.add_node("decide", decide)
        workflow.add_node("validate", check_candidates)
        workflow.add_edge(START, "decide")
        workflow.add_edge("decide", "validate")
        workflow.add_edge("validate", END)
        result = await workflow.compile().ainvoke(
            {
                "context": {
                    "trip": state.model_dump(mode="json"),
                    "event": event.model_dump(mode="json"),
                    "observations": [observation.model_dump(mode="json") for observation in observations],
                }
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
            observations=observations,
            checks=[check for report in reports.values() for check in report.checks],
            trace=[{"node": "decide"}, {"node": "validate", "eligible": len(eligible)}],
            stop_reason=("target_reached" if len(eligible) >= self._target_candidates else "insufficient_valid_candidates"),
        )
