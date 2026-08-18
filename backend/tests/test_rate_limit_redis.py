"""Prove Redis-backed rate limiting is shared across independent 'instances'.

We simulate two API instances by resetting the module-level in-memory buckets
between calls — with the memory backend the second instance would NOT see the
first instance's usage; with Redis it must.

Requires a local Redis (started by CI/dev environment). Skipped when absent.
"""
import uuid

import pytest

from app import security as sec
from app.config import settings
from fastapi import HTTPException


def _redis_available():
    try:
        import redis
        redis.from_url(settings.redis_url, socket_connect_timeout=1).ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="Redis not running")


@pytest.fixture(autouse=True)
def use_redis_backend(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_backend", "redis")
    sec._redis_client = None
    sec._redis_failed_at = 0.0
    yield
    sec._redis_client = None


def test_limit_shared_across_instances():
    key = f"test:{uuid.uuid4().hex}"
    # instance A consumes 3 of limit 3
    for _ in range(3):
        sec.rate_limit(key, 3, 60)
    # simulate a *different* API process: wipe local memory state entirely
    sec._buckets.clear()
    sec._redis_client = None  # fresh connection, as a new process would make
    with pytest.raises(HTTPException) as e:
        sec.rate_limit(key, 3, 60)
    assert e.value.status_code == 429   # Redis remembered across "instances"


def test_different_keys_do_not_interfere():
    k1, k2 = f"t:{uuid.uuid4().hex}", f"t:{uuid.uuid4().hex}"
    for _ in range(3):
        sec.rate_limit(k1, 3, 60)
    sec.rate_limit(k2, 3, 60)  # unaffected


def test_memory_fallback_when_redis_dies(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    sec._redis_client = None
    sec._redis_failed_at = 0.0
    key = f"t:{uuid.uuid4().hex}"
    for _ in range(3):
        sec.rate_limit(key, 3, 60)   # silently degrades to memory
    with pytest.raises(HTTPException):
        sec.rate_limit(key, 3, 60)


def test_sliding_window_no_boundary_burst():
    """The old fixed-window INCR allowed 2x limit across a window rollover.
    The sliding-log implementation must enforce the limit over ANY interval:
    consume the full limit, then verify requests stay blocked until events
    actually age out of the window (not merely until a counter resets)."""
    key = f"t:{uuid.uuid4().hex}"
    limit, window = 5, 2  # 2-second window for a fast test
    for _ in range(limit):
        sec.rate_limit(key, limit, window)
    # immediately over-limit
    with pytest.raises(HTTPException):
        sec.rate_limit(key, limit, window)
    # 1s later — a fixed window keyed on time//window could have rolled over
    # and allowed a fresh burst; sliding window must STILL block.
    import time as _t
    _t.sleep(1.0)
    with pytest.raises(HTTPException):
        sec.rate_limit(key, limit, window)
    # after the full window elapses, events age out and requests flow again
    _t.sleep(1.3)
    sec.rate_limit(key, limit, window)  # must not raise


def test_rejected_requests_do_not_extend_lockout():
    """Sliding-log property: denied attempts must not push the reset further out."""
    key = f"t:{uuid.uuid4().hex}"
    limit, window = 3, 2
    for _ in range(limit):
        sec.rate_limit(key, limit, window)
    import time as _t
    for _ in range(4):  # hammer while blocked
        with pytest.raises(HTTPException):
            sec.rate_limit(key, limit, window)
        _t.sleep(0.1)
    _t.sleep(1.8)  # original events aged out; hammering must not have re-armed it
    sec.rate_limit(key, limit, window)  # must not raise
