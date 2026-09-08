from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from adaptive_trip.domain.models import Item


class Draft(BaseModel):
    """A user-visible schedule draft that cannot change confirmed travel state yet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source_text: str
    items: list[Item] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confirmed: bool = False


class IntakeService:
    async def prepare(self, text: str, preferences: dict[str, object]) -> Draft:
        del preferences
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text must not be blank")
        return Draft(
            id=str(uuid4()),
            source_text=cleaned,
            questions=["일정별 방문 시간과 여행 날짜를 알려주세요."],
            assumptions=[],
            confirmed=False,
        )
