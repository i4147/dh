from __future__ import annotations
from concurrent.futures import (
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeout,
    as_completed,
    wait,
)
import math
import multiprocessing
import multiprocessing.dummy
import time
from typing import Any, Literal
try:
    from concurrent.futures import InterpreterPoolExecutor
except ImportError:  # Python < 3.14
    InterpreterPoolExecutor = None  # type: ignore[misc,assignment]
PoolMethod = Literal[
    "map",
    "map_async",
    "imap",
    "imap_unordered",
    "starmap",
    "starmap_async",
    "apply_async",
]
Backend = Literal[
    "thread",
    "process",
    "cf_thread",
    "cf_process",
    "cf_interpreter",
    "joblib",
]
_DEFAULT_WORKERS = 4
_MP_BACKENDS: frozenset[str] = frozenset({"thread", "process"})
_CF_BACKENDS: frozenset[str] = frozenset({"cf_thread", "cf_process", "cf_interpreter"})
_VALID_BACKENDS: frozenset[str] = _MP_BACKENDS | _CF_BACKENDS | frozenset({"joblib"})
_MP_METHODS: frozenset[str] = frozenset({
    "map",
    "map_async",
    "imap",
    "imap_unordered",
    "starmap",
    "starmap_async",
    "apply_async",
})
_TUPLE_ARG_METHODS: frozenset[str] = frozenset({"starmap", "starmap_async", "apply_async"})
def _chunksize(n_items: int, workers: int) -> int:
    """max(1, min(500, ceil(n / (workers * 4))))."""
    return max(1, min(500, math.ceil(n_items / (workers * 4))))
def _apply_star(fn: Any, args: tuple[Any, ...] | list[Any]) -> Any:
    return fn(*args)
def _validate(backend: str, method: str, items: list[Any]) -> None:
    if backend not in _VALID_BACKENDS:
        msg = f"backend must be one of {sorted(_VALID_BACKENDS)}, got {backend!r}"
        raise ValueError(msg)
    if method not in _MP_METHODS:
        msg = f"method must be one of {sorted(_MP_METHODS)}, got {method!r}"
        raise ValueError(msg)
    if method not in _TUPLE_ARG_METHODS:
        return
    for index, item in enumerate(items):
        if not isinstance(item, (tuple, list)):
            msg = f"items[{index}] must be a tuple/list when method={method!r}; got {type(item).__name__}"
            raise TypeError(msg)
def _drain_imap(iterator: Any, timeout: float | None) -> list[Any]:
    pull = getattr(iterator, "next", None)
    if pull is None:
        return list(iterator)
    results: list[Any] = []
    append = results.append
    while True:
        try:
            append(pull() if timeout is None else pull(timeout))
        except StopIteration:
            return results
def _shutdown_pool(pool: Any, *, terminate: bool) -> None:
    if terminate:
        pool.terminate()
    else:
        pool.close()
    pool.join()
def _in_flight(workers: int) -> int:
    return max(1, workers * 4)
def _run_mp(
    fn: Any,
    items: list[Any],
    method: str,
    kind: str,
    workers: int,
    chunksize: int,
    timeout: float | None,
) -> list[Any]:
    if kind == "thread":
        pool: Any = multiprocessing.dummy.Pool(processes=workers)
    else:
        pool = multiprocessing.get_context("spawn").Pool(processes=workers)
    failed = False
    try:
        if method == "map":
            return list(pool.map(fn, items, chunksize=chunksize))
        if method == "starmap":
            return list(pool.starmap(fn, items, chunksize=chunksize))
        if method == "imap":
            return _drain_imap(pool.imap(fn, items, chunksize=chunksize), timeout)
        if method == "imap_unordered":
            return _drain_imap(pool.imap_unordered(fn, items, chunksize=chunksize), timeout)
        window = _in_flight(workers)
        results: list[Any] = []
        for start in range(0, len(items), window):
            batch = items[start : start + window]
            if method == "map_async":
                results.extend(pool.map_async(fn, batch, chunksize=chunksize).get(timeout=timeout))
            elif method == "starmap_async":
                results.extend(pool.starmap_async(fn, batch, chunksize=chunksize).get(timeout=timeout))
            elif method == "apply_async":
                pending = [pool.apply_async(fn, args) for args in batch]
                results.extend(job.get(timeout=timeout) for job in pending)
                del pending
            else:
                msg = f"unhandled method: {method!r}"
                raise AssertionError(msg)
            del batch
        return results
    except BaseException:
        failed = True
        raise
    finally:
        _shutdown_pool(pool, terminate=failed)
def _take_results(
    futures: list[Future[Any]],
    timeout: float | None,
    *,
    ordered: bool,
) -> list[Any]:
    if not ordered:
        return [item.result() for item in as_completed(futures, timeout=timeout)]
    if timeout is None:
        return [item.result() for item in futures]
    _done, pending = wait(futures, timeout=timeout)
    if pending:
        for item in pending:
            item.cancel()
        msg = f"{len(pending)} of {len(futures)} tasks did not complete"
        raise FuturesTimeout(msg)
    return [item.result() for item in futures]
def _run_futures(
    fn: Any,
    items: list[Any],
    method: str,
    kind: str,
    workers: int,
    chunksize: int,
    timeout: float | None,
) -> list[Any]:
    star = method in _TUPLE_ARG_METHODS
    if kind == "thread":
        executor: Any = ThreadPoolExecutor(max_workers=workers)
    elif kind == "process":
        ctx = multiprocessing.get_context("spawn")
        executor = ProcessPoolExecutor(max_workers=workers, mp_context=ctx)
    else:
        if InterpreterPoolExecutor is None:
            msg = "backend='cf_interpreter' requires Python 3.14+ (concurrent.futures.InterpreterPoolExecutor)"
            raise ImportError(msg)
        executor = InterpreterPoolExecutor(max_workers=workers)
    ordered = method != "imap_unordered"
    streaming = method in {"map", "imap"} and timeout is None and not star
    failed = False
    try:
        if streaming:
            return list(executor.map(fn, items, chunksize=chunksize))
        window = _in_flight(workers)
        results: list[Any] = []
        deadline = None if timeout is None else time.monotonic() + timeout
        for start in range(0, len(items), window):
            batch = items[start : start + window]
            if star:
                futures = [executor.submit(_apply_star, fn, args) for args in batch]
            else:
                futures = [executor.submit(fn, arg) for arg in batch]
            if deadline is None:
                remaining: float | None = None
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    msg = "timed out before the next batch started"
                    raise FuturesTimeout(msg)
            results.extend(_take_results(futures, remaining, ordered=ordered))
            del futures, batch
        return results
    except BaseException:
        failed = True
        raise
    finally:
        try:
            executor.shutdown(wait=not failed, cancel_futures=failed)
        except TypeError:
            executor.shutdown(wait=not failed)
def _run_joblib(
    fn: Any,
    items: list[Any],
    method: str,
    workers: int,
    chunksize: int,
    timeout: float | None,
) -> list[Any]:
    try:
        from joblib import Parallel, delayed
    except ImportError as exc:
        msg = "backend='joblib' requires the 'joblib' package (pip install joblib)"
        raise ImportError(msg) from exc
    if method in _TUPLE_ARG_METHODS:
        jobs = (delayed(fn)(*args) for args in items)
    else:
        jobs = (delayed(fn)(item) for item in items)
    kwargs: dict[str, Any] = {
        "n_jobs": workers,
        "batch_size": chunksize,
        "prefer": "processes",
    }
    if method == "imap_unordered":
        kwargs["return_as"] = "generator_unordered"
    if timeout is not None:
        kwargs["timeout"] = timeout
    with Parallel(**kwargs) as parallel:
        return list(parallel(jobs))
def run_parallel(
    fn: Any,
    items: Any,
    *,
    max_workers: int = _DEFAULT_WORKERS,
    method: PoolMethod = "map",
    backend: Backend = "thread",
    timeout: float | None = None,
) -> list[Any]:
    if not isinstance(items, list):
        items = list(items)
    n_items = len(items)
    if n_items == 0:
        return []
    if max_workers < 1:
        msg = f"max_workers must be >= 1, got {max_workers!r}"
        raise ValueError(msg)
    _validate(backend, method, items)
    workers = min(max_workers, n_items)
    if workers == 1:
        if method in _TUPLE_ARG_METHODS:
            return [fn(*args) for args in items]
        return [fn(item) for item in items]
    chunksize = _chunksize(n_items, workers)
    if backend == "thread":
        return _run_mp(fn, items, method, "thread", workers, chunksize, timeout)
    if backend == "process":
        return _run_mp(fn, items, method, "process", workers, chunksize, timeout)
    if backend == "cf_thread":
        return _run_futures(fn, items, method, "thread", workers, chunksize, timeout)
    if backend == "cf_process":
        return _run_futures(fn, items, method, "process", workers, chunksize, timeout)
    if backend == "cf_interpreter":
        return _run_futures(fn, items, method, "interpreter", workers, chunksize, timeout)
    if backend == "joblib":
        return _run_joblib(fn, items, method, workers, chunksize, timeout)
    msg = f"unhandled backend: {backend!r}"
    raise AssertionError(msg)
__all__ = ["Backend", "PoolMethod", "run_parallel"]
