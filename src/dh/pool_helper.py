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
    if timeout is None:
        return None
    if timeout < 0:
        msg = "timeout must be non-negative"
        raise TimeoutError(msg)
    return time.monotonic() + timeout


def _check_timeout(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        msg = "timed out waiting for multiprocessing results"
        raise TimeoutError(msg)


def as_completed(results: AsyncResults, timeout: float | None = None) -> Iterator[AsyncResult[Any]]:
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
