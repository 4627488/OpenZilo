# SPDX-License-Identifier: MPL-2.0
"""Small asyncio helpers for deadlines and owned background tasks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from typing import Any

from ._errors import TimeoutError

_logger = logging.getLogger(__name__)


def start_background_task(tasks: set[asyncio.Task[Any]], awaitable: Awaitable[Any], label: str) -> None:
    """Keep callback tasks alive and report their failures instead of dropping them."""
    task = asyncio.ensure_future(awaitable)
    tasks.add(task)

    def finished(done: asyncio.Task[Any]) -> None:
        tasks.discard(done)
        if not done.cancelled() and done.exception() is not None:
            _logger.error("%s failed", label, exc_info=done.exception())

    task.add_done_callback(finished)


async def await_before(awaitable: Awaitable[Any], deadline: float, message: str) -> Any:
    task = asyncio.ensure_future(awaitable)
    try:
        done, _pending = await asyncio.wait(
            {task}, timeout=max(0.0, deadline - asyncio.get_running_loop().time()),
        )
    except BaseException:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise
    if not done:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise TimeoutError(message)
    return task.result()


async def acquire_before(lock: asyncio.Lock, deadline: float, message: str) -> None:
    task = asyncio.ensure_future(lock.acquire())

    async def abandon() -> None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if not task.cancelled() and task.exception() is None:
            lock.release()

    try:
        done, _pending = await asyncio.wait(
            {task}, timeout=max(0.0, deadline - asyncio.get_running_loop().time()),
        )
    except BaseException:
        await abandon()
        raise
    if not done:
        await abandon()
        raise TimeoutError(message)
    task.result()
