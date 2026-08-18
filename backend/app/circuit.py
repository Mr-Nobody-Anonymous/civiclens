"""Circuit breakers for external dependencies (AI service, SMTP, storage).

States: closed (normal) -> open (failing; calls short-circuit) -> half-open
(one probe allowed). Prevents cascading latency when a dependency is down —
callers get an immediate CircuitOpen and fall back to their degraded path
(manual review / skipped email / clear upload error) instead of hanging.
"""
import threading
import time


class CircuitOpen(Exception):
    pass


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, reset_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at = 0.0
        self._state = "closed"
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "open" and time.time() - self._opened_at >= self.reset_timeout:
                self._state = "half-open"
            return self._state

    def call(self, fn, *args, **kwargs):
        st = self.state
        if st == "open":
            from .metrics import inc
            inc("civiclens_circuit_short_circuits_total", {"circuit": self.name})
            raise CircuitOpen(f"{self.name} circuit is open")
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return result

    def _record_failure(self):
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold or self._state == "half-open":
                self._state = "open"
                self._opened_at = time.time()
                from .metrics import inc
                inc("civiclens_circuit_opened_total", {"circuit": self.name})

    def _record_success(self):
        with self._lock:
            self._failures = 0
            self._state = "closed"


# shared instances
ai_breaker = CircuitBreaker("ai_service", failure_threshold=3, reset_timeout=45)
smtp_breaker = CircuitBreaker("smtp", failure_threshold=3, reset_timeout=120)
storage_breaker = CircuitBreaker("storage", failure_threshold=5, reset_timeout=30)


def breaker_states() -> dict:
    return {b.name: b.state for b in (ai_breaker, smtp_breaker, storage_breaker)}
