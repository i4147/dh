"""AI implementation prompt: Build a small, dependency-free compatibility layer for
``multiprocessing.pool.Pool.apply_async`` that lets standalone command-line tools wait
for completed jobs safely. Keep the worker count fixed, propagate task exceptions when
results are consumed, support timeouts, and expose typed ``as_completed`` and ``wait``
helpers without depending on ``concurrent.futures``.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator
from multiprocessing.pool import AsyncResult
from typing import Any, TypeVar

MAX_WORKERS = 8
POLL_INTERVAL_SECONDS = 0.01
T = TypeVar("T")
type AsyncResults = Iterable[AsyncResult[Any]]
FIRST_COMPLETED = "FIRST_COMPLETED"
ALL_COMPLETED = "ALL_COMPLETED"


def _deadline(timeout: float | None) -> float | None:
    """Return a monotonic deadline, validating the optional timeout."""
    if timeout is None:
        return None
    if timeout < 0:
        raise TimeoutError("timeout must be non-negative")
    return time.monotonic() + timeout


def _check_timeout(deadline: float | None) -> None:
    """Raise once a deadline has elapsed."""
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError("timed out waiting for multiprocessing results")


def as_completed(results: AsyncResults, timeout: float | None = None) -> Iterator[AsyncResult[Any]]:
    """Yield ``apply_async`` results as they become ready.
    ``multiprocessing.pool.AsyncResult`` has no standard completion iterator. This
    polling implementation is deliberately small and avoids busy waiting while
    preserving the common ``concurrent.futures.as_completed`` call shape.
    """
    pending = set(results)
    deadline = _deadline(timeout)
    while pending:
        ready = [result for result in pending if result.ready()]
        if ready:
            for result in ready:
                pending.remove(result)
                yield result
            continue
        _check_timeout(deadline)
        time.sleep(POLL_INTERVAL_SECONDS)


def wait(
    results: AsyncResults,
    timeout: float | None = None,
    return_when: str = ALL_COMPLETED,
) -> tuple[set[AsyncResult[Any]], set[AsyncResult[Any]]]:
    """Return completed and unfinished ``apply_async`` results.
    The supported ``return_when`` values mirror the names used by
    ``concurrent.futures`` so migrated scripts can retain their control flow.
    """
    pending = set(results)
    done = {result for result in pending if result.ready()}
    if return_when == FIRST_COMPLETED and done:
        return done, pending - done
    deadline = _deadline(timeout)
    while pending - done:
        if return_when == FIRST_COMPLETED and done:
            break
        _check_timeout(deadline)
        time.sleep(POLL_INTERVAL_SECONDS)
        done.update(result for result in pending if result.ready())
    return done, pending - done
