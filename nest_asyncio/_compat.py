"""Interpreter-specific asyncio compatibility helpers for nest_asyncio.

Some behaviors here are adapted from Chaoses-Ib/nest-asyncio2 and then
rewritten for the original nest_asyncio codebase and public API.
"""

from __future__ import annotations

import asyncio
import asyncio.events as events
import sys
from contextlib import suppress
from typing import Awaitable, Callable, Protocol

IS_PY312_PLUS = sys.version_info >= (3, 12, 0)
IS_PY314_PLUS = sys.version_info >= (3, 14, 0)


class CurrentTaskFn(Protocol):
    def __call__(
        self, loop: asyncio.AbstractEventLoop | None = None
    ) -> asyncio.Task[object] | None: ...


class AllTasksFn(Protocol):
    def __call__(
        self, loop: asyncio.AbstractEventLoop | None = None
    ) -> set[asyncio.Task[object]]: ...


def _get_task_type(name: str) -> type[asyncio.Task[object]]:
    value = getattr(asyncio.tasks, name)
    if not isinstance(value, type):
        raise TypeError(f"asyncio.tasks.{name} is not a task type")
    return value


def _get_future_type(name: str) -> type[asyncio.Future[object]]:
    value = getattr(asyncio.futures, name)
    if not isinstance(value, type):
        raise TypeError(f"asyncio.futures.{name} is not a future type")
    return value


def get_event_loop_for_apply() -> asyncio.AbstractEventLoop | None:
    """Return the loop nest_asyncio.apply() should patch, if any."""
    if not IS_PY312_PLUS:
        return asyncio.get_event_loop()
    if not IS_PY314_PLUS:
        loop = events._get_running_loop()
        if loop is None:
            policy = events.get_event_loop_policy()
            loop = policy._local._loop
        return loop
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        return None


def legacy_get_event_loop(stacklevel: int = 3) -> asyncio.AbstractEventLoop:
    """Mirror the pre-3.14 get_event_loop behavior used by patched asyncio."""
    loop = events._get_running_loop()
    if loop is None:
        loop = events.get_event_loop_policy().get_event_loop()
    return loop


def patch_task_and_future_types() -> None:
    """Use pure-Python Task/Future implementations where that remains safe."""
    if sys.version_info < (3, 6, 0) or IS_PY314_PLUS:
        return
    py_task = _get_task_type("_PyTask")
    py_future = _get_future_type("_PyFuture")
    setattr(asyncio.tasks, "_CTask", py_task)
    setattr(asyncio.tasks, "Task", py_task)
    setattr(asyncio, "Task", py_task)
    setattr(asyncio.futures, "_CFuture", py_future)
    setattr(asyncio.futures, "Future", py_future)
    setattr(asyncio, "Future", py_future)
    if hasattr(asyncio.tasks, "_py_current_task"):
        current_task_fn: CurrentTaskFn = getattr(asyncio.tasks, "_py_current_task")
        asyncio.tasks.current_task = asyncio.current_task = current_task_fn
    if hasattr(asyncio.tasks, "_py_all_tasks"):
        all_tasks_fn: AllTasksFn = getattr(asyncio.tasks, "_py_all_tasks")
        asyncio.tasks.all_tasks = asyncio.all_tasks = all_tasks_fn


def patch_asyncio_get_event_loop() -> None:
    """Patch asyncio.get_event_loop only where the legacy behavior is needed."""
    if sys.version_info < (3, 9, 0) or IS_PY314_PLUS:
        return
    setattr(events, "_get_event_loop", legacy_get_event_loop)
    events.get_event_loop = asyncio.get_event_loop = legacy_get_event_loop


def run(
    main: Awaitable[object],
    *,
    debug: bool | None = False,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
    patch_loop: Callable[[asyncio.AbstractEventLoop], None],
) -> object:
    """Patched asyncio.run implementation with version-aware semantics."""
    if not IS_PY312_PLUS:
        if loop_factory is not None:
            raise TypeError("run() got an unexpected keyword argument 'loop_factory'")
        loop = asyncio.get_event_loop()
        loop.set_debug(bool(debug))
        task = asyncio.ensure_future(main)
        try:
            return loop.run_until_complete(task)
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    loop.run_until_complete(task)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = get_event_loop_for_apply()
        if current_loop is None:
            if loop_factory is None:
                loop_factory = asyncio.new_event_loop
            current_loop = loop_factory()
            asyncio.set_event_loop(current_loop)
        loop = current_loop

    patch_loop(loop)
    if debug is not None:
        loop.set_debug(debug)
    task = asyncio.ensure_future(main, loop=loop)
    try:
        return loop.run_until_complete(task)
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                loop.run_until_complete(task)
