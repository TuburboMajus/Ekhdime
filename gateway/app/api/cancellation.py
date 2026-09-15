"""In-memory registry so `DELETE /api/v1/requests/{id}` can cancel an
in-flight `query`/`query/audio` call.

MVP per the root README section 31: basic, but subprocesses must never
become uncontrolled zombies -- cancelling the tracked asyncio.Task
propagates into the agent adapters, which kill their subprocess on
CancelledError (see app/agents/copilot.py / claude.py).
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager

_INFLIGHT: dict[str, asyncio.Task] = {}


@contextmanager
def track(request_id: str, task: asyncio.Task):
    _INFLIGHT[request_id] = task
    try:
        yield
    finally:
        _INFLIGHT.pop(request_id, None)


def cancel(request_id: str) -> bool:
    task = _INFLIGHT.get(request_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True
