from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class ToolHttpError(Exception):
    status_code: int | None
    message: str

    def __str__(self) -> str:
        return self.message


async def retry_request(
    operation: Callable[[], Awaitable[T]],
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_retries: int = 2,
) -> T:
    """Retry only transient provider failures with bounded exponential delays."""
    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except ToolHttpError as error:
            if not _is_retryable(error.status_code) or attempt == max_retries:
                raise
            await sleep(0.5 * (2**attempt))
    raise RuntimeError("retry loop exited unexpectedly")


def _is_retryable(status_code: int | None) -> bool:
    return status_code is None or status_code == 429 or 500 <= status_code <= 599
