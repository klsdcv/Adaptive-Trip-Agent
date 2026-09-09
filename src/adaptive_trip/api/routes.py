from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from adaptive_trip.agent.graph import Replanner
from adaptive_trip.api.schemas import (
    DecisionInput,
    DraftConfirmationInput,
    DraftInput,
    ReplanInput,
)
from adaptive_trip.domain.models import ChangeEvent, Proposal, TripState
from adaptive_trip.services.decisions import DecisionService
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

    @router.post("/drafts", response_model=Draft, status_code=status.HTTP_201_CREATED)
    async def create_draft(body: DraftInput) -> Draft:
        try:
            return await intake_service.prepare(body.text, body.preferences)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

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

    @router.post("/trips/{trip_id}/events", response_model=Proposal, status_code=status.HTTP_202_ACCEPTED)
    async def replan(trip_id: str, body: ReplanInput) -> Proposal:
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
