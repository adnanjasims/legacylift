"""In-process job event fan-out for SSE. One queue per subscriber."""

from __future__ import annotations

import json
from collections.abc import Iterator
from queue import Empty, Queue
from typing import Any

TERMINAL = frozenset({"completed", "failed", "dead_lettered"})


class EventHub:
    def __init__(self) -> None:
        self._subs: dict[str, list[Queue[dict[str, Any]]]] = {}

    def publish(self, job_id: str, event: dict[str, Any]) -> None:
        for q in list(self._subs.get(job_id, [])):
            q.put(event)

    def subscribe(self, job_id: str) -> Queue[dict[str, Any]]:
        q: Queue[dict[str, Any]] = Queue()
        self._subs.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, q: Queue[dict[str, Any]]) -> None:
        holders = self._subs.get(job_id)
        if holders is None:
            return
        if q in holders:
            holders.remove(q)
        if not holders:
            del self._subs[job_id]


def sse_pack(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def iter_sse(
    hub: EventHub,
    job_id: str,
    snapshot: dict[str, Any],
) -> Iterator[str]:
    """Yield the current job, then live events until a terminal status."""
    q = hub.subscribe(job_id)
    try:
        yield sse_pack(snapshot)
        if snapshot.get("status") in TERMINAL:
            return
        while True:
            try:
                event = q.get(timeout=15)
            except Empty:
                yield ": keepalive\n\n"
                continue
            yield sse_pack(event)
            if event.get("status") in TERMINAL:
                return
    finally:
        hub.unsubscribe(job_id, q)
