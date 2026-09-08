from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_free_text_without_time_becomes_an_unconfirmed_draft() -> None:
    from adaptive_trip.services.intake import IntakeService

    draft = await IntakeService().prepare("내일 미술관 갔다가 저녁", {})

    assert not draft.confirmed
    assert draft.items == []
    assert "시간" in draft.questions[0]


@pytest.mark.asyncio
async def test_blank_text_is_rejected() -> None:
    from adaptive_trip.services.intake import IntakeService

    with pytest.raises(ValueError, match="text"):
        await IntakeService().prepare("   ", {})
