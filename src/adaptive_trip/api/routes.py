from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from adaptive_trip.agent.graph import Replanner
from adaptive_trip.api.schemas import (
    DecisionInput,
    DraftConfirmationInput,
    DraftInput,
    EventInput,
    ModeInput,
    ReplanInput,
    RunStatus,
)
from adaptive_trip.domain.models import ChangeEvent, Proposal, TripState
from adaptive_trip.services.decisions import DecisionService
from adaptive_trip.services.events import EventConflictError, EventValidationError, TripEventService
from adaptive_trip.services.intake import Draft, IntakeService
from adaptive_trip.storage.repository import Repository


def build_router(
    repository: Repository,
    decisions: DecisionService | None = None,
    replanner: Replanner | None = None,
    clock: Callable[[], datetime] | None = None,
    intake: IntakeService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api")
    intake_service = intake or IntakeService()
    event_service = TripEventService()

    @router.post("/drafts", response_model=Draft, status_code=status.HTTP_201_CREATED)
    async def create_draft(body: DraftInput) -> Draft:
        try:
            return await intake_service.prepare(body.text, body.preferences)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.post(
        "/drafts/{draft_id}/confirm",
        response_model=TripState,
        status_code=status.HTTP_201_CREATED,
    )
    async def confirm_draft(draft_id: str, body: DraftConfirmationInput) -> TripState:
        try:
            trip = await intake_service.confirm(
                draft_id,
                body.confirmed_fields,
                body.request_id,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Draft not found.") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

        try:
            return repository.get(trip.id)
        except KeyError:
            repository.create(trip)
            return trip

    @router.post("/trips", response_model=TripState, status_code=status.HTTP_201_CREATED)
    def create_trip(trip: TripState) -> TripState:
        try:
            repository.create(trip)
        except Exception as error:
            if "UNIQUE constraint failed" in str(error):
                raise HTTPException(status_code=409, detail="Trip already exists.") from error
            raise
        return trip

    @router.get("/trips/{trip_id}", response_model=TripState)
    def get_trip(trip_id: str) -> TripState:
        try:
            return repository.get(trip_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Trip not found.") from error

    @router.patch("/trips/{trip_id}/mode", response_model=TripState)
    def set_mode(trip_id: str, body: ModeInput) -> TripState:
        try:
            trip = repository.get(trip_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Trip not found.") from error
        if repository.event_exists(trip_id, f"{trip_id}:{body.request_id}"):
            return repository.get(trip_id)
        try:
            updated, event = event_service.build(
                trip,
                kind="preference",
                payload={"travel_mode": body.enabled},
                expected_version=body.expected_version,
                request_id=body.request_id,
                at=clock() if clock is not None else trip.now,
            )
            stored, changed = repository.apply_event(
                updated, event, expected_version=body.expected_version
            )
        except EventConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except EventValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if not changed:
            return repository.get(trip_id)
        return stored

    @router.get("/trips/{trip_id}/proposals", response_model=list[Proposal])
    def get_pending_proposals(trip_id: str) -> list[Proposal]:
        try:
            repository.get(trip_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Trip not found.") from error
        return repository.pending_proposals(trip_id)

    @router.get("/trips/{trip_id}/notifications", response_model=list[ChangeEvent])
    def get_notifications(trip_id: str) -> list[ChangeEvent]:
        try:
            repository.get(trip_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Trip not found.") from error
        return repository.events(trip_id)

    @router.get("/runs/{run_id}", response_model=RunStatus)
    def get_run(run_id: str) -> RunStatus:
        try:
            record = repository.get_run(run_id)
            return RunStatus.model_validate({
                "run_id": record["id"],
                "trip_id": record["trip_id"],
                "status": record["status"],
                "proposal_id": record["proposal_id"],
                "error": record["error"],
            })
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Run not found.") from error

    @router.post("/trips/{trip_id}/decisions")
    async def decide(trip_id: str, body: DecisionInput):
        if decisions is None:
            raise HTTPException(status_code=503, detail="Decision service is unavailable.")
        result = await decisions.decide(
            trip_id,
            body.proposal_id,
            body.candidate_id,
            body.action,
            body.request_id,
        )
        if result.status == "invalid":
            raise HTTPException(status_code=404, detail="Proposal or trip not found.")
        return result

    @router.post(
        "/trips/{trip_id}/events",
        response_model=RunStatus | Proposal,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def replan(trip_id: str, body: EventInput | ReplanInput) -> RunStatus | Proposal:
        if isinstance(body, EventInput):
            try:
                trip = repository.get(trip_id)
            except KeyError as error:
                raise HTTPException(status_code=404, detail="Trip not found.") from error
            duplicate = repository.event_exists(
                trip_id, f"{trip_id}:{body.request_id}"
            )
            if duplicate:
                run_id = str(uuid4())
                repository.create_run(run_id, trip_id)
                repository.update_run(run_id, status="completed")
                run = repository.get_run(run_id)
                return RunStatus.model_validate({
                    "run_id": run["id"],
                    "trip_id": run["trip_id"],
                    "status": run["status"],
                    "proposal_id": run["proposal_id"],
                    "error": run["error"],
                })
            try:
                updated, event = event_service.build(
                    trip,
                    kind=body.kind,
                    payload=body.payload,
                    expected_version=body.expected_version,
                    request_id=body.request_id,
                    at=clock() if clock is not None else trip.now,
                )
                stored, changed = repository.apply_event(
                    updated, event, expected_version=body.expected_version
                )
            except EventConflictError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            except EventValidationError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            except ValueError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error

            run_id = str(uuid4())
            repository.create_run(run_id, trip_id)
            if changed and replanner is not None and clock is not None:
                try:
                    result = await replanner.run(stored, event, [], clock())
                    if result.proposal is not None:
                        repository.save_proposal(result.proposal)
                        repository.update_run(
                            run_id,
                            status="completed",
                            proposal_id=result.proposal.id,
                        )
                    else:
                        repository.update_run(run_id, status="completed")
                except Exception as error:
                    repository.update_run(run_id, status="failed", error=str(error))
            else:
                repository.update_run(run_id, status="completed")
            run = repository.get_run(run_id)
            return RunStatus.model_validate({
                "run_id": run["id"],
                "trip_id": run["trip_id"],
                "status": run["status"],
                "proposal_id": run["proposal_id"],
                "error": run["error"],
            })

        if replanner is None or clock is None:
            raise HTTPException(status_code=503, detail="Replanning service is unavailable.")
        if body.event.trip_id != trip_id:
            raise HTTPException(status_code=422, detail="Event trip does not match the route.")
        try:
            trip = repository.get(trip_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Trip not found.") from error
        result = await replanner.run(trip, body.event, body.observations, clock())
        if result.proposal is None:
            raise HTTPException(status_code=422, detail="No replanning proposal was generated.")
        repository.save_proposal(result.proposal)
        return result.proposal

    return router
