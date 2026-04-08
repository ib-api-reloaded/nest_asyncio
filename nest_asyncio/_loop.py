"""Loop-patching helpers extracted from nest_asyncio's hot path."""

from __future__ import annotations

import asyncio
import sys
from typing import Protocol

IS_PY314_PLUS = sys.version_info >= (3, 14, 0)


class CurrentTaskSwapper(Protocol):
    def __call__(
        self, loop: object, task: asyncio.Task[object] | None
    ) -> asyncio.Task[object] | None: ...


class DrainableLoop(Protocol):
    _ready: object

    def _run_once(self) -> None: ...


def _swap_current_task(
    loop: object, task: asyncio.Task[object] | None
) -> asyncio.Task[object] | None:
    swap_current_task: CurrentTaskSwapper = getattr(asyncio.tasks, "_swap_current_task")
    return swap_current_task(loop, task)


def preempt_current_task(
    loop: object, curr_tasks: dict[object, asyncio.Task[object]]
) -> asyncio.Task[object] | None:
    """Temporarily clear the current task for nested handle execution."""
    if not IS_PY314_PLUS:
        return curr_tasks.pop(loop, None)
    try:
        return _swap_current_task(loop, None)
    except KeyError:
        return None


def restore_current_task(
    loop: object,
    curr_task: asyncio.Task[object] | None,
    curr_tasks: dict[object, asyncio.Task[object]],
) -> None:
    """Restore the current task after nested handle execution."""
    if curr_task is None:
        return
    if not IS_PY314_PLUS:
        curr_tasks[loop] = curr_task
        return
    _swap_current_task(loop, curr_task)


def drain_ready(loop: DrainableLoop) -> None:
    """Run one more loop tick to process callbacks queued during completion."""
    if loop._ready:
        loop._run_once()
