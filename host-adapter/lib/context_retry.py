"""Retry and checkpoint primitives for Codex-side Context model jobs."""

from __future__ import annotations

import time
from datetime import datetime, timezone


RETRYABLE_ERRORS = (TimeoutError, ConnectionError)


def run_with_retry(worker, *, max_attempts=5, base_delay=1.0, sleep=time.sleep):
    """Run one idempotent job, retrying transient failures with backoff.

    The worker receives the 1-based attempt number. The returned receipt never
    labels a failed job as generated; callers can checkpoint it and resume.
    """
    attempts = []
    max_attempts = max(1, int(max_attempts))
    for attempt in range(1, max_attempts + 1):
        started = datetime.now(timezone.utc).isoformat()
        try:
            result = worker(attempt)
            return {"status": "succeeded", "attempt": attempt, "attempts": attempts + [{"attempt": attempt, "status": "succeeded", "started_at": started}], "result": result}
        except Exception as error:  # model adapters may expose provider-specific transient errors
            retryable = isinstance(error, RETRYABLE_ERRORS) or bool(getattr(error, "retryable", False))
            record = {"attempt": attempt, "status": "failed", "retryable": retryable, "error": type(error).__name__, "started_at": started}
            attempts.append(record)
            if not retryable or attempt >= max_attempts:
                return {"status": "failed", "attempt": attempt, "attempts": attempts, "error": type(error).__name__}
            sleep(max(0.0, float(base_delay)) * (2 ** (attempt - 1)))
    return {"status": "failed", "attempt": max_attempts, "attempts": attempts, "error": "retry_loop_exhausted"}
