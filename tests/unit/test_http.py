from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_retry_retries_a_transient_status_twice_before_success() -> None:
    from adaptive_trip.tools.http import ToolHttpError, retry_request

    attempts = 0
    delays: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ToolHttpError(status_code=503, message="provider unavailable")
        return "ok"

    async def sleep(delay: float) -> None:
        delays.append(delay)

    assert await retry_request(operation, sleep=sleep) == "ok"
    assert attempts == 3
    assert delays == [0.5, 1.0]


@pytest.mark.asyncio
async def test_retry_does_not_retry_an_authentication_error() -> None:
    from adaptive_trip.tools.http import ToolHttpError, retry_request

    attempts = 0

    async def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise ToolHttpError(status_code=401, message="invalid key")

    with pytest.raises(ToolHttpError):
        await retry_request(operation, sleep=lambda _: None)

    assert attempts == 1
