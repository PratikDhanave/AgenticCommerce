"""A tiny in-process event bus.

The ADK Runner already yields Events, but the UI wants a narrative: which
agent spoke, which tool ran, what the mandate decided, and why. Tools push
semantic events here and the SSE endpoint drains them in order.
"""

from __future__ import annotations

import asyncio
import contextvars
import itertools
import time
from typing import Any

_seq = itertools.count(1)
current_session: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_session", default="demo"
)

# session_id -> queue of UI events
_queues: dict[str, asyncio.Queue] = {}


def queue_for(session_id: str) -> asyncio.Queue:
    if session_id not in _queues:
        _queues[session_id] = asyncio.Queue()
    return _queues[session_id]


def reset(session_id: str) -> None:
    _queues[session_id] = asyncio.Queue()


def emit(kind: str, **payload: Any) -> dict:
    """Push a UI event onto the current session's queue."""
    event = {
        "seq": next(_seq),
        "at": round(time.time(), 3),
        "kind": kind,
        **payload,
    }
    try:
        queue_for(current_session.get()).put_nowait(event)
    except RuntimeError:
        pass
    return event
