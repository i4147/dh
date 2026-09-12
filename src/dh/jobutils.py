"""Parallel file processing utilities.

This module provides a collection of helpers for running a function over many
items (typically :class:`pathlib.Path` objects) using multiprocessing or
multithreading. It includes thin wrappers around :mod:`multiprocessing.Pool`,
:class:`concurrent.futures.ProcessPoolExecutor`,
:class:`concurrent.futures.ThreadPoolExecutor`, and an optional ``joblib``
backend.

The :func:`mpf3` function is the most feature-rich entry point: it performs
bounded submission of tasks, supports per-task timeouts, and reports a
:class:`ParallelSummary` describing successes, failures, and timeouts.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import (
    FIRST_COMPLETED,
    Executor,
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
    wait,
)
from dataclasses import dataclass
from functools import partial
from multiprocessing import get_context
from pathlib import Path
from typing import Any, ParamSpec, Protocol, TypeVar, Callable


T = TypeVar("T")
R = TypeVar("R")
P = ParamSpec("P")

MAX_WORKERS = 8
DEFAULT_TIMEOUT = 30
_MP_CONTEXT = get_context("spawn")
ExecutorFactory = Callable[..., Executor]


def _call_with_index[R](func: Callable[[Path], R], indexed_file: tuple[int, Path]) -> tuple[int, R]:
    """Invoke ``func`` with a :class:`Path` while preserving its index."""
    idx, file = indexed_file
    return idx, func(file)


def _get_pool(workers: int = MAX_WORKERS) -> Any:
    """Create a ``multiprocessing`` pool using the module's spawn context.

    Args:
        workers: Number of worker processes.

    Returns:
        A ``multiprocessing.pool.Pool`` instance.
    """
    return _MP_CONTEXT.Pool(workers)


def mpf_async[**P, R](
    func: Callable[P, R],
    files: Iterable[Path],
    workers: int = MAX_WORKERS,
    timeout: int = DEFAULT_TIMEOUT,
    *args: P.args,
    **kwargs: P.kwargs,
) -> list[R | None]:
    """Run ``func`` over ``files`` using ``Pool.apply_async``.

    Each file is submitted independently, and results are collected in the
    original order. Failures are logged and recorded as ``None``.

    Args:
        func: Callable to apply to each file.
        files: Iterable of :class:`Path` objects.
        workers: Number of worker processes.
        timeout: Per-task timeout in seconds.
        *args: Extra positional arguments forwarded to ``func``.
        **kwargs: Extra keyword arguments forwarded to ``func``.

    Returns:
        List of results (or ``None`` for failures) in input order.
    """
    files_list = list(files)
    if not files_list:
        return []

    with _get_pool(workers) as pool:
        async_results = [pool.apply_async(func, (file, *args), kwargs) for file in files_list]
        results: list[R | None] = []
        for i, async_result in enumerate(async_results):
            try:
                results.append(async_result.get(timeout=timeout))
            except Exception as e:
                print(f"File {i} ({files_list[i]}) failed: {e}")
                results.append(None)
    return results


def mpf_map[R](
    func: Callable[[Path], R],
    files: Iterable[Path],
    workers: int = MAX_WORKERS,
    chunksize: int = 1,
) -> list[R | None]:
    """Apply ``func`` to ``files`` with ``Pool.map``.

    Args:
        func: Callable accepting a :class:`Path`.
        files: Iterable of :class:`Path` objects.
        workers: Number of worker processes.
        chunksize: Number of items per task chunk.

    Returns:
        List of results in input order; ``None`` entries on failure.
    """
    files_list = list(files)
    if not files_list:
        return []

    with _get_pool(workers) as pool:
        try:
            return list(pool.map(func, files_list, chunksize=chunksize))
        except Exception as e:
            print(f"Pool.map failed: {e}")
            return [None] * len(files_list)


def mpf_imap[R](
    func: Callable[[Path], R],
    files: Iterable[Path],
    workers: int = MAX_WORKERS,
    chunksize: int = 1,
    ordered: bool = True,
) -> list[R | None]:
    """Apply ``func`` to ``files`` with ``Pool.imap`` / ``imap_unordered``.

    Args:
        func: Callable accepting a :class:`Path`.
        files: Iterable of :class:`Path` objects.
        workers: Number of worker processes.
        chunksize: Number of items per task chunk.
        ordered: If ``True`` use ``imap``; otherwise ``imap_unordered``.

    Returns:
        List of results.
    """
    files_list = list(files)
    if not files_list:
        return []

    results: list[R | None] = []

    with _get_pool(workers) as pool:
        imap_func = pool.imap if ordered else pool.imap_unordered
        for result in imap_func(func, files_list, chunksize=chunksize):
            results.append(result)
    return results


def mpf_imapu[R](
    func: Callable[[Path], R],
    files: Iterable[Path],
    workers: int = MAX_WORKERS,
    chunksize: int = 1,
) -> list[R | None]:
    """..."""
    files_list = list(files)
    if not files_list:
        return []

    results: list[R | None] = [None] * len(files_list)
    bound = partial(_call_with_index, func)
    indexed = list(enumerate(files_list))

    with _get_pool(workers) as pool:
        for idx, result in pool.imap_unordered(bound, indexed, chunksize=chunksize):
            results[idx] = result
    return results


def mpf_starmap[**P, R](
    func: Callable[P, R],
    files: Iterable[Path],
    extra_args: Sequence[tuple] | None = None,
    workers: int = MAX_WORKERS,
) -> list[R | None]:
    """Apply ``func`` to ``files`` with ``Pool.starmap``.

    ``extra_args`` allows passing additional positional arguments per file.
    Each entry in ``extra_args`` is splatted after the file argument.

    Args:
        func: Callable whose first parameter is a :class:`Path`.
        files: Iterable of :class:`Path` objects.
        extra_args: Optional per-file extra positional argument tuples.
        workers: Number of worker processes.

    Returns:
        List of results; ``None`` entries on failure.

    Raises:
        ValueError: If ``extra_args`` length differs from ``files`` length.
    """
    files_list = list(files)
    if not files_list:
        return []

    if extra_args is None:
        extra_args = [() for _ in files_list]
    elif len(extra_args) != len(files_list):
        raise ValueError("extra_args length must match files length")

    task_args = [(file, *args) for file, args in zip(files_list, extra_args)]

    with _get_pool(workers) as pool:
        try:
            return list(pool.starmap(func, task_args))
        except Exception as e:
            print(f"Pool.starmap failed: {e}")
            return [None] * len(files_list)


def mpf_ppe[R](
    func: Callable[[Path], R],
    files: Iterable[Path],
    workers: int = MAX_WORKERS,
    timeout: int = DEFAULT_TIMEOUT,
    use_as_completed: bool = False,
) -> list[R | None]:
    """Process ``files`` with :class:`ProcessPoolExecutor`.

    Args:
        func: Callable accepting a :class:`Path`.
        files: Iterable of :class:`Path` objects.
        workers: Maximum number of worker processes.
        timeout: Timeout forwarded to ``Future.result`` / ``as_completed``.
        use_as_completed: If ``True`` consume futures via ``as_completed``;
            otherwise iterate the futures dict directly.

    Returns:
        List of results in input order; ``None`` entries on failure.
    """
    files_list = list(files)
    if not files_list:
        return []

    results: list[R | None] = [None] * len(files_list)

    with ProcessPoolExecutor(max_workers=workers, mp_context=_MP_CONTEXT) as executor:
        futures = {executor.submit(func, file): i for i, file in enumerate(files_list)}

        if use_as_completed:
            from concurrent.futures import as_completed

            iterator: Iterable[Future[R]] = as_completed(futures, timeout=timeout)
        else:
            iterator = iter(futures)

        for future in iterator:
            idx = futures[future]
            try:
                results[idx] = future.result(timeout=timeout)
            except Exception as e:
                print(f"File {idx} ({files_list[idx]}) failed: {e}")
                results[idx] = None
    return results


def mpf_tpe[R](
    func: Callable[[Path], R],
    files: Iterable[Path],
    workers: int = MAX_WORKERS,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[R | None]:
    """Process ``files`` with :class:`ThreadPoolExecutor`.

    Args:
        func: Callable accepting a :class:`Path`.
        files: Iterable of :class:`Path` objects.
        workers: Maximum number of worker threads.
        timeout: Timeout forwarded to ``Future.result``.

    Returns:
        List of results in input order; ``None`` entries on failure.
    """
    files_list = list(files)
    if not files_list:
        return []

    results: list[R | None] = [None] * len(files_list)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(func, file): i for i, file in enumerate(files_list)}
        for future in futures:
            idx = futures[future]
            try:
                results[idx] = future.result(timeout=timeout)
            except Exception as e:
                print(f"File {idx} ({files_list[idx]}) failed: {e}")
                results[idx] = None
    return results


@dataclass
class ParallelSummary:
    """Aggregate statistics for a :func:`mpf3` run.

    Attributes:
        total: Total number of items processed.
        succeeded: Number of items that returned without error.
        failed: Number of items that raised an exception.
        timed_out: Number of items that exceeded the timeout.
    """

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    timed_out: int = 0

    @property
    def success_rate(self) -> float:
        """Return the success ratio as a percentage (0.0 when empty)."""
        return (self.succeeded / self.total * 100) if self.total > 0 else 0.0


class _ExecutorFactory(Protocol):
    """Protocol matching the :class:`concurrent.futures.Executor` constructors."""

    def __call__(
        self,
        max_workers: int | None = ...,
        **kwargs: Any,
    ) -> Executor: ...


def mpf3[T, R](
    func: Callable[[T], tuple[R, str | None]],
    items: Iterable[T],
    *,
    max_workers: int = MAX_WORKERS,
    max_pending_factor: int = 8,
    timeout: float | None = DEFAULT_TIMEOUT,
    on_success: Callable[[T, R], None] | None = None,
    on_error: Callable[[T, str], None] | None = None,
    on_timeout: Callable[[T], None] | None = None,
    executor_type: ExecutorFactory = ProcessPoolExecutor,
    executor_kwargs: dict[str, Any] | None = None,
) -> ParallelSummary:
    """Run ``func`` over ``items`` with bounded concurrency and timeouts.

    ``func`` must return a ``(result, error)`` tuple. When ``error`` is not
    ``None`` the item is counted as failed; otherwise it is counted as a
    success. Exceptions raised by ``func`` and per-task timeouts are handled
    separately.

    Args:
        func: Callable returning ``(result, error)`` for each item.
        items: Iterable of items to process.
        max_workers: Maximum number of concurrent workers.
        max_pending_factor: Multiplier applied to ``max_workers`` to decide
            how many futures may be in flight at once.
        timeout: Per-task timeout in seconds, or ``None`` to disable.
        on_success: Callback invoked as ``on_success(item, result)``.
        on_error: Callback invoked as ``on_error(item, message)``.
        on_timeout: Callback invoked as ``on_timeout(item)`` on timeout.
        executor_type: Executor class to instantiate.
        executor_kwargs: Extra keyword arguments passed to the executor.

    Returns:
        A :class:`ParallelSummary` describing the run.
    """
    if not items:
        return ParallelSummary()

    if executor_kwargs is None:
        executor_kwargs = {}
    if executor_type is ProcessPoolExecutor:
        executor_kwargs.setdefault("mp_context", _MP_CONTEXT)

    max_pending = max(max_pending_factor * max_workers, max_workers)
    summary = ParallelSummary()
    item_iterator = iter(items)
    pending: dict[Future[tuple[R, str | None]], tuple[T, float]] = {}

    with executor_type(max_workers=max_workers, **executor_kwargs) as executor:
        exhausted = False

        # Prime the pending queue.
        while len(pending) < max_pending and not exhausted:
            try:
                item = next(item_iterator)
                future = executor.submit(func, item)
                pending[future] = (item, time.time())
            except StopIteration:
                exhausted = True

        while pending:
            done, _ = wait(pending.keys(), return_when=FIRST_COMPLETED)

            for future in done:
                item, start_time = pending.pop(future)
                summary.total += 1

                try:
                    if timeout is not None:
                        elapsed = time.time() - start_time
                        remaining_timeout = max(0.0, timeout - elapsed)
                        if remaining_timeout == 0:
                            raise FutureTimeoutError(f"Task timed out after {timeout}s")

                        result, error = future.result(timeout=remaining_timeout)
                    else:
                        result, error = future.result()

                    if error is not None:
                        summary.failed += 1
                        if on_error:
                            on_error(item, error)
                    else:
                        summary.succeeded += 1
                        if on_success:
                            on_success(item, result)

                except FutureTimeoutError:
                    summary.timed_out += 1
                    future.cancel()
                    if on_timeout:
                        on_timeout(item)
                    elif on_error:
                        on_error(item, f"Timeout after {timeout}s")

                except Exception as exc:
                    summary.failed += 1
                    error_msg = f"{type(exc).__name__}: {exc}"
                    if on_error:
                        on_error(item, error_msg)

            if not exhausted:
                while len(pending) < max_pending:
                    try:
                        item = next(item_iterator)
                        future = executor.submit(func, item)
                        pending[future] = (item, time.time())
                    except StopIteration:
                        exhausted = True
                        break

    return summary


def mpf(
    worker_fn: Callable,
    items: list[Any],
    num_jobs: int = 1,
    *worker_args: Any,
    **worker_kwargs: Any,
) -> list[Any]:
    """Run ``worker_fn`` over ``items`` using ``Pool.apply_async``.

    Args:
        worker_fn: Callable applied to each item.
        items: Items to process.
        num_jobs: Number of worker processes.
        *worker_args: Extra positional arguments for ``worker_fn``.
        **worker_kwargs: Extra keyword arguments for ``worker_fn``.

    Returns:
        List of results in input order.
    """
    if not items:
        return []

    with _get_pool(num_jobs) as pool:
        async_results = [pool.apply_async(worker_fn, args=(item, *worker_args), kwds=worker_kwargs) for item in items]
        return [result.get() for result in async_results]


def mpf2(
    worker_fn: Callable,
    items: list[Any],
    num_jobs: int = 1,
    *worker_args: Any,
    **worker_kwargs: Any,
) -> list[Any]:
    """Alias for :func:`mpf` retained for backwards compatibility."""
    return mpf(worker_fn, items, num_jobs, *worker_args, **worker_kwargs)


def mpf_joblib(
    process_function: Callable,
    files: list[Path],
    n_jobs: int = -1,
    **kwargs: Any,
) -> list[Any]:
    """Run ``process_function`` over ``files`` using ``joblib.Parallel``.

    Args:
        process_function: Callable accepting a string path.
        files: List of :class:`Path` objects.
        n_jobs: ``joblib`` worker count (``-1`` uses all CPUs).
        **kwargs: Extra keyword arguments forwarded to ``process_function``.

    Returns:
        List of results in input order.
    """
    from joblib import Parallel, delayed

    file_strings = [str(f) for f in files]
    return Parallel(n_jobs=n_jobs)(delayed(process_function)(file_str, **kwargs) for file_str in file_strings)


def mpf_ppe_ac(
    func: Callable,
    files: Iterable[Path],
    workers: int = MAX_WORKERS,
    timeout: int = 30,
) -> list[Any]:
    """Run ``func`` over ``files`` with ``ProcessPoolExecutor`` + ``as_completed``.

    Args:
        func: Callable accepting a :class:`Path`.
        files: Iterable of :class:`Path` objects.
        workers: Maximum number of worker processes.
        timeout: Timeout forwarded to ``as_completed``.

    Returns:
        List of results in input order; ``None`` entries on failure.
    """
    from concurrent.futures import as_completed

    files_list = list(files)
    if not files_list:
        return []
    results: list[Any] = [None] * len(files_list)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(func, file): i for i, file in enumerate(files_list)}
        for future in as_completed(futures, timeout=timeout):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                print(f"File {idx} ({files_list[idx]}) failed: {e}")
                results[idx] = None
    return results
