from __future__ import annotations

import functools
import multiprocessing
import multiprocessing.dummy  # Thread-backed Pool exposing the same API as mp.Pool
import os
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# --------------------------------------------------------------------------- #
# Public type aliases
# --------------------------------------------------------------------------- #
PoolMethod = Literal["map", "imap", "imap_unordered", "apply", "apply_async", "starmap"]
Backend = Literal["thread", "process", "cf_thread", "cf_process", "joblib"]
# --------------------------------------------------------------------------- #
# Module-level constants
# --------------------------------------------------------------------------- #
_DEFAULT_WORKERS = 8
_ENV_VAR = "GGET_MAX_WORKERS"
_MP_BACKENDS: frozenset[str] = frozenset({"thread", "process"})
_CF_BACKENDS: frozenset[str] = frozenset({"cf_thread", "cf_process"})
_VALID_BACKENDS: frozenset[str] = _MP_BACKENDS | _CF_BACKENDS | frozenset({"joblib"})
# ``multiprocessing.Pool`` exposes a few extra methods that the other backends
# do not have equivalents for.
_MP_METHODS: frozenset[str] = frozenset({"map", "imap", "imap_unordered", "apply", "apply_async", "starmap"})
# Methods available for every backend.
_COMMON_METHODS: frozenset[str] = frozenset({"map", "imap", "imap_unordered", "starmap"})
# Methods whose *items* are tuples of positional args (``fn(*item)``).
_TUPLE_ARG_METHODS: frozenset[str] = frozenset({"starmap", "apply", "apply_async"})


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _resolve_max_workers(max_workers: int | None, n_items: int) -> int:
    """Resolve worker count from arg / env / default and cap it at ``n_items``."""
    if max_workers is None:
        raw = os.getenv(_ENV_VAR)
        try:
            max_workers = int(raw) if raw else _DEFAULT_WORKERS
        except (TypeError, ValueError):
            max_workers = _DEFAULT_WORKERS
    if max_workers < 1:
        msg = f"max_workers must be >= 1, got {max_workers!r}"
        raise ValueError(msg)
    return min(max_workers, n_items)


def _validate(backend: str, method: str, chunksize: int, items: list[Any]) -> None:
    """Reject bad backend/method/chunksize/item combinations up front."""
    if backend not in _VALID_BACKENDS:
        msg = f"backend must be one of {sorted(_VALID_BACKENDS)}, got {backend!r}"
        raise ValueError(msg)
    valid_methods = _MP_METHODS if backend in _MP_BACKENDS else _COMMON_METHODS
    if method not in valid_methods:
        msg = f"method must be one of {sorted(valid_methods)} for backend={backend!r}; got {method!r}"
        raise ValueError(msg)
    if not isinstance(chunksize, int) or isinstance(chunksize, bool) or chunksize < 1:
        msg = f"chunksize must be an int >= 1, got {chunksize!r}"
        raise ValueError(msg)
    if method in _TUPLE_ARG_METHODS:
        for i, item in enumerate(items):
            if not isinstance(item, (tuple, list)):
                msg = f"items[{i}] must be a tuple/list when method={method!r}; got {type(item).__name__}"
                raise TypeError(msg)


def _apply_star(fn: Callable[..., Any], args: tuple[Any, ...]) -> Any:
    """Module-level ``fn(*args)`` shim — picklable for ProcessPool / loky."""
    return fn(*args)


def _drain_imap(iterator, timeout: float | None) -> list[Any]:
    """Exhaust an ``IMapIterator`` honouring a per-item timeout (may be ``None``)."""
    results: list[Any] = []
    while True:
        try:
            results.append(iterator.next(timeout))  # type: ignore[attr-defined]
        except StopIteration:
            return results


# --------------------------------------------------------------------------- #
# Backend runners
# --------------------------------------------------------------------------- #
def _run_mp(
    fn: Callable[..., Any],
    items: list[Any],
    method: str,
    kind: str,
    max_workers: int,
    chunksize: int,
    timeout: float | None,
) -> list[Any]:
    """Run through ``multiprocessing.dummy.Pool`` (threads) or ``multiprocessing.Pool``."""
    if kind == "thread":
        pool = multiprocessing.dummy.Pool(processes=max_workers)
    else:
        pool = multiprocessing.Pool(processes=max_workers)
    try:
        if method == "map":
            if timeout is None:
                return pool.map(fn, items, chunksize=chunksize)
            return pool.map_async(fn, items, chunksize=chunksize).get(timeout=timeout)
        if method == "starmap":
            if timeout is None:
                return pool.starmap(fn, items, chunksize=chunksize)
            return pool.starmap_async(fn, items, chunksize=chunksize).get(timeout=timeout)
        if method == "imap":
            return _drain_imap(pool.imap(fn, items, chunksize=chunksize), timeout)
        if method == "imap_unordered":
            return _drain_imap(pool.imap_unordered(fn, items, chunksize=chunksize), timeout)
        if method == "apply":
            if timeout is None:
                return [pool.apply(fn, args) for args in items]
            async_results = [pool.apply_async(fn, args) for args in items]
            return [r.get(timeout=timeout) for r in async_results]
        if method == "apply_async":
            async_results = [pool.apply_async(fn, args) for args in items]
            return [r.get(timeout=timeout) for r in async_results]
        msg = f"unhandled method: {method!r}"
        raise AssertionError(msg)
    except BaseException:
        # Terminate immediately so __exit__ doesn't block on pending work.
        pool.terminate()
        pool.join()
        raise
    else:
        pool.close()
        pool.join()


def _run_futures(
    fn: Callable[..., Any],
    items: list[Any],
    method: str,
    kind: str,
    max_workers: int,
    chunksize: int,
    timeout: float | None,
) -> list[Any]:
    """Run through ``concurrent.futures.ThreadPoolExecutor`` or ``ProcessPoolExecutor``."""
    from concurrent.futures import (
        ProcessPoolExecutor,
        ThreadPoolExecutor,
        TimeoutError as FuturesTimeout,
        as_completed,
        wait,
    )

    Executor = ThreadPoolExecutor if kind == "thread" else ProcessPoolExecutor
    call = functools.partial(_apply_star, fn) if method == "starmap" else fn
    executor = Executor(max_workers=max_workers)
    try:
        # Fast path: no timeout → let executor.map handle the ordering
        # (chunksize is honoured only by ProcessPoolExecutor; ignored for threads).
        if method in ("map", "imap") and timeout is None:
            return list(executor.map(call, items, chunksize=chunksize))
        futures = [executor.submit(call, x) for x in items]
        if method in ("map", "imap"):
            # Bounded batch wait; preserves input order on return.
            _, pending = wait(futures, timeout=timeout)
            if pending:
                msg = f"{len(pending)} of {len(futures)} tasks did not complete"
                raise FuturesTimeout(msg)
            return [f.result() for f in futures]
        # imap_unordered → completion order.
        return [f.result() for f in as_completed(futures, timeout=timeout)]
    except BaseException:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:  # Python < 3.9
            executor.shutdown(wait=False)
        raise
    else:
        executor.shutdown(wait=True)


def _run_joblib(
    fn: Callable[..., Any],
    items: list[Any],
    method: str,
    max_workers: int,
    chunksize: int,
    timeout: float | None,
) -> list[Any]:
    """Run through ``joblib.Parallel`` (loky process backend by default)."""
    try:
        from joblib import Parallel, delayed
    except ImportError as exc:  # pragma: no cover
        msg = "backend='joblib' requires the 'joblib' package (pip install joblib)"
        raise ImportError(msg) from exc
    if method == "starmap":
        jobs = (delayed(fn)(*args) for args in items)
    else:
        jobs = (delayed(fn)(item) for item in items)
    kwargs: dict[str, Any] = {"n_jobs": max_workers, "batch_size": chunksize}
    if method == "imap_unordered":
        # ``generator_unordered`` requires joblib >= 1.3.
        kwargs["return_as"] = "generator_unordered"
    if timeout is not None:
        # NOTE: joblib applies this timeout per-task, not per-batch.
        kwargs["timeout"] = timeout
    with Parallel(**kwargs) as parallel:
        return list(parallel(jobs))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def run_parallel(
    fn: Callable[..., Any],
    items: Iterable[Any],
    *,
    max_workers: int | None = None,
    method: PoolMethod = "map",
    backend: Backend = "thread",
    chunksize: int = 1,
    timeout: float | None = None,
) -> list[Any]:
    """Apply ``fn`` to each item using the selected pool backend.
    Designed primarily for I/O-bound work (typically per-ID HTTP calls, where
    per-call latency is dominated by network RTT). Process-based backends are
    available for CPU-bound workloads — remember that ``fn`` and every item
    must then be picklable.
    Parameters
    ----------
    fn:
        Callable applied to each item. When ``method`` is one of
        ``starmap``, ``apply``, ``apply_async``, each item is unpacked as
        positional arguments (``fn(*item)``).
    items:
        Iterable of arguments. For ``starmap`` / ``apply`` / ``apply_async``
        each element must itself be a tuple/list of positional arguments.
    max_workers:
        Pool size. Defaults to the ``GGET_MAX_WORKERS`` env var, or ``8``.
        Capped at ``len(items)``; a value of ``1`` runs serially in-process
        (no pool is created).
    method:
        Which worker strategy to use:
        * ``"map"``            – ordered, eager (blocks until all done)
        * ``"imap"``           – ordered, lazy
        * ``"imap_unordered"`` – results in completion order
        * ``"starmap"``        – like ``map`` but unpacks each item as args
        * ``"apply"``          – one call per item (only for ``thread``/``process``)
        * ``"apply_async"``    – async ``apply`` per item (only for ``thread``/``process``)
    backend:
        Worker implementation:
        * ``"thread"``      – ``multiprocessing.dummy.Pool``     (default)
        * ``"process"``     – ``multiprocessing.Pool``
        * ``"cf_thread"``   – ``concurrent.futures.ThreadPoolExecutor``
        * ``"cf_process"``  – ``concurrent.futures.ProcessPoolExecutor``
        * ``"joblib"``      – ``joblib.Parallel`` (loky process backend)
    chunksize:
        Batch size hint. Honoured by ``thread`` / ``process`` (all methods
        that accept it), ``cf_process``'s ``map``, and joblib (as
        ``batch_size``). Ignored by ``cf_thread``.
    timeout:
        Optional timeout in seconds. Semantics:
        * ``imap`` / ``imap_unordered`` on the multiprocessing backends:
          per-item timeout.
        * All other backends / methods: overall batch timeout.
        * joblib: per-task timeout (joblib's own convention).
        * ``None`` (default) waits forever.
    Returns
    -------
    list
        One result per input item. Order follows the input for every method
        except ``imap_unordered``, which yields results in completion order.
    Raises
    ------
    ValueError
        Invalid ``backend`` / ``method`` / ``max_workers`` / ``chunksize``.
    TypeError
        ``method`` requires tuple arguments but an item is not a
        ``tuple`` / ``list``.
    ImportError
        ``backend='joblib'`` selected but joblib is not installed.
    BaseException
        Any exception raised inside ``fn`` propagates to the caller; the
        pool/executor is torn down before re-raising.
    """
    # Materialise once — we need len() and may iterate multiple times.
    items = list(items)
    if not items:
        return []
    # ---- Argument validation -------------------------------------------------
    _validate(backend, method, chunksize, items)
    takes_arg_tuples = method in _TUPLE_ARG_METHODS
    max_workers = _resolve_max_workers(max_workers, len(items))
    # ---- Serial fast path (no pool overhead for single-worker jobs) ----------
    if max_workers == 1:
        if takes_arg_tuples:
            return [fn(*args) for args in items]
        return [fn(item) for item in items]
    # ---- Dispatch to the chosen backend --------------------------------------
    if backend in _MP_BACKENDS:
        return _run_mp(fn, items, method, backend, max_workers, chunksize, timeout)
    if backend in _CF_BACKENDS:
        kind = "thread" if backend == "cf_thread" else "process"
        return _run_futures(fn, items, method, kind, max_workers, chunksize, timeout)
    if backend == "joblib":
        return _run_joblib(fn, items, method, max_workers, chunksize, timeout)
    msg = f"unhandled backend: {backend!r}"
    raise AssertionError(msg)  # pragma: no cover
