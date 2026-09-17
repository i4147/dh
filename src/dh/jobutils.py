"""Parallel execution helpers.

A single dispatcher — :func:`run_parallel` — over:

* ``multiprocessing.Pool``   (``map``, ``map_async``, ``starmap``,
  ``starmap_async``, ``imap``, ``imap_unordered``, ``apply``,
  ``apply_async``)
* ``concurrent.futures``     (``ProcessPoolExecutor``, ``ThreadPoolExecutor``)
* ``joblib``                 (optional dependency)

Features:

* Bounded in-flight submission — a slow consumer or a hung worker can't
  blow up memory by having every task queued as a ``Future`` at once.
* Per-task deadlines — the dispatcher enforces a wall-clock deadline per
  item, not just a timeout on ``Future.result()``.
* Optional progress / error hooks for the executor backends.
* ``return_exceptions=True`` to collect failures instead of aborting.

Designed for Python 3.12+ on Linux; ``MAX_WORKERS`` is tuned for 8 cores.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import multiprocessing.pool  # noqa: F401  (needed so ``mp.pool.Pool`` resolves)
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
    wait,
)
from enum import Enum
from functools import partial
from typing import Any

__all__ = [
    "DEFAULT_CHUNKSIZE",
    "DEFAULT_EXECUTOR_CHUNKSIZE",
    "MAX_WORKERS",
    "PoolMethod",
    "mpf",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

#: Default worker count. Tuned for an 8-core Linux box.
MAX_WORKERS: int = 8

#: Default chunk size for :class:`multiprocessing.Pool` methods.
#: ``None`` lets the pool auto-compute it (one chunk per ~``4 * workers``
#: items), matching the stdlib default since Python 3.5.
DEFAULT_CHUNKSIZE: int | None = None

#: Default chunk size for :class:`ProcessPoolExecutor.map`.
#: The stdlib default is ``1``; we mirror it.
DEFAULT_EXECUTOR_CHUNKSIZE: int = 1

#: Alias for the executor classes accepted by :func:`_run_executor`.
ExecutorType = type[ProcessPoolExecutor] | type[ThreadPoolExecutor]


# ---------------------------------------------------------------------------
# Method enumeration
# ---------------------------------------------------------------------------


class PoolMethod(str, Enum):
    """Every supported execution backend."""

    # multiprocessing.Pool
    MAP = "map"
    MAP_ASYNC = "map_async"
    STARMAP = "starmap"
    STARMAP_ASYNC = "starmap_async"
    IMAP = "imap"
    IMAP_UNORDERED = "imap_unordered"
    APPLY = "apply"
    APPLY_ASYNC = "apply_async"

    # concurrent.futures / joblib
    JOBLIB = "joblib"
    PROCESS_POOL = "process_pool"
    THREAD_POOL = "thread_pool"

    @classmethod
    def parse(cls, value: str | PoolMethod) -> PoolMethod:
        """Coerce ``value`` (enum or case-insensitive string) to a member.

        Raises
        ------
        ValueError
            If ``value`` doesn't match any known method name.
        """
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).lower())
        except ValueError as exc:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"unknown method {value!r}; expected one of: {valid}") from exc

    @property
    def is_mp_pool(self) -> bool:
        """``True`` if this method routes through :class:`multiprocessing.Pool`."""
        return self.value in _MP_POOL_METHODS


_MP_POOL_METHODS = frozenset(
    {
        "map",
        "map_async",
        "starmap",
        "starmap_async",
        "imap",
        "imap_unordered",
        "apply",
        "apply_async",
    }
)


# ---------------------------------------------------------------------------
# multiprocessing.Pool backend
# ---------------------------------------------------------------------------


def _dispatch_mp_pool(
    pool: mp.pool.Pool,
    method: PoolMethod,
    func: Callable[..., Any],
    items: list[Any],
    chunksize: int | None,
) -> list[Any]:
    """Route one mp.Pool method to the corresponding pool primitive."""
    if method is PoolMethod.MAP:
        return pool.map(func, items, chunksize=chunksize)
    if method is PoolMethod.MAP_ASYNC:
        return pool.map_async(func, items, chunksize=chunksize).get()

    if method in (PoolMethod.STARMAP, PoolMethod.STARMAP_ASYNC):
        # ``starmap`` treats each item as a tuple of positional args.
        args = [item if isinstance(item, tuple) else (item,) for item in items]
        if method is PoolMethod.STARMAP:
            return pool.starmap(func, args, chunksize=chunksize)
        return pool.starmap_async(func, args, chunksize=chunksize).get()

    if method is PoolMethod.IMAP:
        return list(pool.imap(func, items, chunksize=chunksize))
    if method is PoolMethod.IMAP_UNORDERED:
        return list(pool.imap_unordered(func, items, chunksize=chunksize))

    if method is PoolMethod.APPLY:
        # Note: ``apply`` is synchronous and serial — included for
        # completeness, not for throughput.
        return [pool.apply(func, args=(item,)) for item in items]
    if method is PoolMethod.APPLY_ASYNC:
        futs = [pool.apply_async(func, args=(item,)) for item in items]
        return [f.get() for f in futs]

    raise AssertionError(f"unhandled mp.pool method: {method}")


def _run_mp_pool(
    method: PoolMethod,
    func: Callable[..., Any],
    items: Iterable[Any],
    *,
    workers: int,
    chunksize: int | None,
    initializer: Callable[..., Any] | None,
    initargs: Sequence[Any],
    maxtasksperchild: int | None,
    context: str | None,
) -> list[Any]:
    """Spin up a :class:`multiprocessing.Pool` and dispatch to it."""
    items_list = list(items)
    if not items_list:
        return []

    ctx = mp.get_context(context)  # ``None`` -> platform default (fork on Linux)
    pool_kwargs: dict[str, Any] = {"processes": workers}
    if initializer is not None:
        pool_kwargs["initializer"] = initializer
        pool_kwargs["initargs"] = tuple(initargs)
    if maxtasksperchild is not None:
        pool_kwargs["maxtasksperchild"] = maxtasksperchild

    with ctx.Pool(**pool_kwargs) as pool:
        return _dispatch_mp_pool(pool, method, func, items_list, chunksize)


# ---------------------------------------------------------------------------
# concurrent.futures backend (process + thread)
# ---------------------------------------------------------------------------


def _submit_args(item: Any, unpack: bool) -> tuple[Any, ...]:
    """Shape a single item into positional args for ``executor.submit``."""
    if unpack:
        return item if isinstance(item, tuple) else (item,)
    return (item,)


def _run_executor(
    executor_cls: ExecutorType,
    func: Callable[..., Any],
    items: Iterable[Any],
    *,
    workers: int,
    chunksize: int | None,
    unpack: bool,
    initializer: Callable[..., Any] | None,
    initargs: Sequence[Any],
    maxtasksperchild: int | None,
    timeout: float | None,
    return_exceptions: bool,
    max_pending: int | None,
    on_progress: Callable[[int, Any], None] | None,
) -> list[Any]:
    """Run ``func`` over ``items`` with a ``concurrent.futures`` executor.

    Two paths:

    * **Fast path** — no timeout, no progress hook, no per-item error
      collection, and no manual unpack: hand everything to
      ``executor.map`` and let the stdlib do chunking and ordering.
    * **Slow path** — bounded in-flight queue with optional per-task
      deadlines and completion callbacks.
    """
    is_process = executor_cls is ProcessPoolExecutor

    kwargs: dict[str, Any] = {"max_workers": workers}
    if initializer is not None:
        kwargs["initializer"] = initializer
        kwargs["initargs"] = tuple(initargs)
    if maxtasksperchild is not None:
        if not is_process:
            raise ValueError("maxtasksperchild is only supported by ProcessPoolExecutor")
        kwargs["max_tasks_per_child"] = maxtasksperchild

    # ------------------------------------------------------------------
    # Fast path
    # ------------------------------------------------------------------
    if not unpack and timeout is None and on_progress is None and not return_exceptions and max_pending is None:
        with executor_cls(**kwargs) as ex:
            if is_process:
                cs = chunksize if chunksize is not None else DEFAULT_EXECUTOR_CHUNKSIZE
                return list(ex.map(func, items, chunksize=cs))
            # ThreadPoolExecutor.map has no chunksize parameter.
            return list(ex.map(func, items))

    # ------------------------------------------------------------------
    # Slow path: bounded in-flight queue
    # ------------------------------------------------------------------
    items_list = list(items)
    n = len(items_list)
    if n == 0:
        return []

    cap = max_pending if max_pending is not None else max(4 * workers, workers)
    cap = max(cap, 1)

    results: list[Any] = [None] * n
    item_iter = iter(enumerate(items_list))
    pending: dict[Future[Any], tuple[int, float]] = {}
    exhausted = False

    def _fill(ex: ProcessPoolExecutor | ThreadPoolExecutor) -> None:
        """Top up the pending set up to ``cap`` futures."""
        nonlocal exhausted
        while len(pending) < cap and not exhausted:
            try:
                idx, item = next(item_iter)
            except StopIteration:
                exhausted = True
                return
            fut = ex.submit(func, *_submit_args(item, unpack))
            pending[fut] = (idx, time.monotonic())

    with executor_cls(**kwargs) as ex:
        _fill(ex)

        while pending:
            # Wait until either the earliest deadline or the first completion.
            if timeout is not None:
                earliest = min(t for _, t in pending.values())
                wait_for = max(0.0, timeout - (time.monotonic() - earliest))
            else:
                wait_for = None

            done, _ = wait(
                pending.keys(),
                return_when=FIRST_COMPLETED,
                timeout=wait_for,
            )

            # Successful / raising completions.
            for fut in done:
                info = pending.pop(fut, None)
                if info is None:
                    continue  # already reaped via timeout branch
                idx = info[0]
                try:
                    results[idx] = fut.result()
                except Exception as exc:
                    logger.debug("task %d failed: %r", idx, exc)
                    results[idx] = exc
                if on_progress is not None:
                    on_progress(idx, results[idx])

            # Deadline enforcement on whatever is still pending.
            if timeout is not None:
                now = time.monotonic()
                timed_out = [f for f, (_, t) in pending.items() if now - t >= timeout]
                for fut in timed_out:
                    idx = pending.pop(fut)[0]
                    fut.cancel()
                    err = FutureTimeoutError(f"task {idx} exceeded {timeout}s")
                    logger.debug("task %d timed out after %.3fs", idx, timeout)
                    results[idx] = err
                    if on_progress is not None:
                        on_progress(idx, err)

            _fill(ex)

    # If the caller didn't ask for exceptions, surface the first failure
    # (by item index) rather than returning a mixed list.
    if not return_exceptions:
        for r in results:
            if isinstance(r, BaseException):
                raise r

    return results


# ---------------------------------------------------------------------------
# joblib backend
# ---------------------------------------------------------------------------


def _run_joblib(
    func: Callable[..., Any],
    items: Iterable[Any],
    workers: int | None,
    unpack: bool,
) -> list[Any]:
    """Dispatch through :class:`joblib.Parallel`.

    ``workers=None`` means *all CPUs* (joblib's ``n_jobs=-1``), which is the
    sensible default for a parallel dispatcher — unlike joblib's own default
    of ``1`` (serial).
    """
    try:
        from joblib import Parallel, delayed  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover
        raise ImportError("the 'joblib' backend requires joblib — `pip install joblib`") from exc

    n_jobs = -1 if workers is None else workers
    items_list = list(items)

    if unpack:
        return Parallel(n_jobs=n_jobs)(
            delayed(func)(*(item if isinstance(item, tuple) else (item,))) for item in items_list
        )
    return Parallel(n_jobs=n_jobs)(delayed(func)(item) for item in items_list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def mpf(
    func: Callable[..., Any],
    items: Iterable[Any],
    method: str | PoolMethod = PoolMethod.IMAP_UNORDERED,
    *,
    workers: int = MAX_WORKERS,
    chunksize: int | None = DEFAULT_CHUNKSIZE,
    unpack: bool = False,
    func_args: Sequence[Any] = (),
    func_kwargs: dict[str, Any] | None = None,
    initializer: Callable[..., Any] | None = None,
    initargs: Sequence[Any] = (),
    maxtasksperchild: int | None = None,
    context: str | None = None,
    timeout: float | None = None,
    return_exceptions: bool = False,
    max_pending: int | None = None,
    on_progress: Callable[[int, Any], None] | None = None,
) -> list[Any]:
    """Run ``func`` over ``items`` using the requested backend.

    Parameters
    ----------
    func, items
        The callable and its inputs. ``Path`` objects are fine.
    method
        Execution backend. Accepts a :class:`PoolMethod` or its string value:

        * ``multiprocessing.Pool`` — ``"map"``, ``"map_async"``,
          ``"starmap"``, ``"starmap_async"``, ``"imap"``,
          ``"imap_unordered"`` (default), ``"apply"``, ``"apply_async"``.
        * ``concurrent.futures`` — ``"process_pool"``, ``"thread_pool"``.
        * Third-party — ``"joblib"`` (requires ``pip install joblib``).
    workers
        Worker count. Defaults to :data:`MAX_WORKERS` (8).
    chunksize
        Batch size hint. Honoured by Pool methods and
        ``ProcessPoolExecutor``; ignored by ``ThreadPoolExecutor`` and
        joblib. Default ``None`` = auto for Pool, ``1`` for the process
        executor.
    unpack
        If ``True``, each item is spread as positional args to ``func``
        (starmap-style). Only meaningful for the executor and joblib
        backends — the ``multiprocessing`` ``starmap*`` variants already do
        this.
    func_args, func_kwargs
        Bound to ``func`` via :func:`functools.partial` before dispatch —
        i.e. they are placed *before* each item in the argument list. For
        trailing options, prefer ``func_kwargs``.
    initializer, initargs
        Per-worker setup. Supported by ``multiprocessing.Pool`` and both
        executors; not by joblib.
    maxtasksperchild
        Recycle workers after N tasks. ``multiprocessing.Pool`` and
        ``ProcessPoolExecutor`` only (the latter requires Python 3.11+).
    context
        ``"fork"``, ``"spawn"``, ``"forkserver"`` — ``multiprocessing`` only.
        ``None`` uses the platform default (fork on Linux).
    timeout
        Wall-clock seconds allowed per item. Tasks that exceed it are
        cancelled and their result slot becomes a :class:`TimeoutError` (or
        raises, if ``return_exceptions=False``). Only the executor backends
        honour this — Pool methods raise ``ValueError`` if it's set.
    return_exceptions
        If ``False`` (default), the first exception raised by any item is
        re-raised after all work completes. If ``True``, exceptions are
        stored in the result list as if they were return values.
    max_pending
        Cap on simultaneously in-flight tasks for the executor backends.
        Defaults to ``4 * workers``. Ignored on the fast path.
    on_progress
        Optional ``callback(index, result_or_exception)`` fired as each
        item completes. Executor backends only.

    Returns
    -------
    list
        Results in input order for every method except ``imap_unordered``,
        which yields in completion order.
    """
    if not callable(func):
        raise TypeError("`func` must be callable")

    pool_method = PoolMethod.parse(method)

    if func_args or func_kwargs:
        func = partial(func, *func_args, **(func_kwargs or {}))

    # ---- multiprocessing.Pool --------------------------------------------
    if pool_method.is_mp_pool:
        if timeout is not None:
            raise ValueError(
                "timeout is only supported by the executor backends "
                "('process_pool' / 'thread_pool'); use one of those or "
                "handle deadlines inside your worker"
            )
        return _run_mp_pool(
            pool_method,
            func,
            items,
            workers=workers,
            chunksize=chunksize,
            initializer=initializer,
            initargs=initargs,
            maxtasksperchild=maxtasksperchild,
            context=context,
        )

    # ---- joblib ----------------------------------------------------------
    if pool_method is PoolMethod.JOBLIB:
        if initializer is not None or maxtasksperchild is not None:
            raise ValueError(
                "the 'joblib' backend does not support initializer/maxtasksperchild; use 'process_pool' instead"
            )
        if timeout is not None:
            raise ValueError("the 'joblib' backend does not support timeout")
        return _run_joblib(func, items, workers, unpack)

    # ---- concurrent.futures ---------------------------------------------
    if pool_method is PoolMethod.PROCESS_POOL:
        return _run_executor(
            ProcessPoolExecutor,
            func,
            items,
            workers=workers,
            chunksize=chunksize,
            unpack=unpack,
            initializer=initializer,
            initargs=initargs,
            maxtasksperchild=maxtasksperchild,
            timeout=timeout,
            return_exceptions=return_exceptions,
            max_pending=max_pending,
            on_progress=on_progress,
        )

    if pool_method is PoolMethod.THREAD_POOL:
        if maxtasksperchild is not None:
            raise ValueError("ThreadPoolExecutor does not support maxtasksperchild")
        return _run_executor(
            ThreadPoolExecutor,
            func,
            items,
            workers=workers,
            chunksize=chunksize,
            unpack=unpack,
            initializer=initializer,
            initargs=initargs,
            maxtasksperchild=None,
            timeout=timeout,
            return_exceptions=return_exceptions,
            max_pending=max_pending,
            on_progress=on_progress,
        )

    raise AssertionError(f"unhandled method: {pool_method}")
