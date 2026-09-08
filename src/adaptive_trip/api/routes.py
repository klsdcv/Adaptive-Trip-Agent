from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from adaptive_trip.api.schemas import DecisionInput
from adaptive_trip.domain.models import TripState
from adaptive_trip.services.decisions import DecisionService
from adaptive_trip.storage.repository import Repository


def build_router(repository: Repository, decisions: DecisionService | None = None) -> APIRouter:
    router = APIRouter(prefix="/api")

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

    return router
