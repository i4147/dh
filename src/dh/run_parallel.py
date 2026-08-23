from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import (FIRST_COMPLETED, Executor, Future,
                                ProcessPoolExecutor, wait)
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class ParallelSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0


def _submit_until_full(
    executor: Executor,
    items: Iterator[T],
    func: Callable[[T], tuple[R, str | None]],
    pending: dict[Future[tuple[R, str | None]], T],
    max_pending: int,
) -> bool:
    exhausted = False

    while len(pending) < max_pending:
        try:
            item = next(items)
        except StopIteration:
            exhausted = True
            break

        pending[executor.submit(func, item)] = item

    return exhausted


def mpf3(
    func: Callable[[T], tuple[R, str | None]],
    items: Iterable[T],
    *,
    max_workers: int | None = None,
    max_pending_factor: int = 4,
    on_success: Callable[[T, R], None] | None = None,
    on_error: Callable[[T, str], None] | None = None,
    executor_factory: Callable[[int], Executor] | None = None,
) -> ParallelSummary:

    if max_workers is None:
        max_workers = min(8, os.cpu_count() or 1)

    max_workers = max(1, max_workers)

    if executor_factory is None:
        executor_factory = ProcessPoolExecutor

    max_pending = max(max_pending_factor * max_workers, max_workers)

    summary = ParallelSummary()
    item_iterator = iter(items)
    pending: dict[Future[tuple[R, str | None]], T] = {}

    with executor_factory(max_workers) as executor:
        exhausted = _submit_until_full(
            executor,
            item_iterator,
            func,
            pending,
            max_pending,
        )

        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)

            for future in done:
                item = pending.pop(future)
                summary.total += 1

                try:
                    result, error = future.result()
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    result = None  # type: ignore[assignment]

                if error is not None:
                    summary.failed += 1
                    if on_error:
                        on_error(item, error)
                else:
                    summary.succeeded += 1
                    if on_success:
                        on_success(item, result)

            if not exhausted:
                exhausted = _submit_until_full(
                    executor,
                    item_iterator,
                    func,
                    pending,
                    max_pending,
                )

    return summary
