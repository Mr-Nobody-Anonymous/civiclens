"""Real-time notification hub (Server-Sent Events).

SSE over the existing session auth — no new infra, works through nginx, and
degrades gracefully: the frontend keeps its 30s polling as fallback. Each
connected user has an asyncio queue; notify() pushes events to it.

Single-process design (matches the dev/thread deployment). For multi-instance
production, point publish() at Redis pub/sub — the API contract stays identical.
"""
import asyncio
import json
import logging
from collections import defaultdict
from typing import AsyncGenerator

log = logging.getLogger("civiclens.events")

_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)
_loop: asyncio.AbstractEventLoop | None = None


def register_loop(loop: asyncio.AbstractEventLoop):
    global _loop
    _loop = loop


def publish(user_id: str, event: dict):
    """Thread-safe publish (jobs run in worker threads)."""
    if _loop is None:
        return
    def _put():
        for q in _queues.get(user_id, []):
            if q.qsize() < 100:
                q.put_nowait(event)
    try:
        _loop.call_soon_threadsafe(_put)
    except RuntimeError:
        pass


async def subscribe(user_id: str) -> AsyncGenerator[str, None]:
    q: asyncio.Queue = asyncio.Queue()
    _queues[user_id].append(q)
    try:
        yield f"event: hello\ndata: {json.dumps({'ok': True})}\n\n"
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=25)
                yield f"event: notification\ndata: {json.dumps(ev)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"     # comment frame keeps proxies happy
    finally:
        try:
            _queues[user_id].remove(q)
        except ValueError:
            pass
