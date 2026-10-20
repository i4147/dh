from __future__ import annotations

import functools
import multiprocessing
import multiprocessing.dummy
import os
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
PoolMethod = Literal["map", "imap", "imap_unordered", "apply", "apply_async", "starmap"]
Backend = Literal["thread", "process", "cf_thread", "cf_process", "joblib"]
_DEFAULT_WORKERS = 8
_ENV_VAR = "GGET_MAX_WORKERS"
_MP_BACKENDS: frozenset[str] = frozenset({"thread", "process"})
_CF_BACKENDS: frozenset[str] = frozenset({"cf_thread", "cf_process"})
_VALID_BACKENDS: frozenset[str] = _MP_BACKENDS | _CF_BACKENDS | frozenset({"joblib"})
_MP_METHODS: frozenset[str] = frozenset({"map", "imap", "imap_unordered", "apply", "apply_async", "starmap"})
_COMMON_METHODS: frozenset[str] = frozenset({"map", "imap", "imap_unordered", "starmap"})
_TUPLE_ARG_METHODS: frozenset[str] = frozenset({"starmap", "apply", "apply_async"})


def _resolve_max_workers(max_workers: int | None, n_items: int) -> int:
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
    return fn(*args)


def _drain_imap(iterator, timeout: float | None) -> list[Any]:
    results: list[Any] = []
    while True:
        try:
            results.append(iterator.next(timeout))
        except StopIteration:
            return results


def _run_mp(
    fn: Callable[..., Any],
    items: list[Any],
    method: str,
    kind: str,
    max_workers: int,
    chunksize: int,
    timeout: float | None,
) -> list[Any]:
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
    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FuturesTimeout
    from concurrent.futures import as_completed, wait

    Executor = ThreadPoolExecutor if kind == "thread" else ProcessPoolExecutor
    call = functools.partial(_apply_star, fn) if method == "starmap" else fn
    executor = Executor(max_workers=max_workers)
    try:
        if method in ("map", "imap") and timeout is None:
            return list(executor.map(call, items, chunksize=chunksize))
        futures = [executor.submit(call, x) for x in items]
        if method in ("map", "imap"):
            _, pending = wait(futures, timeout=timeout)
            if pending:
                msg = f"{len(pending)} of {len(futures)} tasks did not complete"
                raise FuturesTimeout(msg)
            return [f.result() for f in futures]
        return [f.result() for f in as_completed(futures, timeout=timeout)]
    except BaseException:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
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
    try:
        from joblib import Parallel, delayed
    except ImportError as exc:
        msg = "backend='joblib' requires the 'joblib' package (pip install joblib)"
        raise ImportError(msg) from exc
    if method == "starmap":
        jobs = (delayed(fn)(*args) for args in items)
    else:
        jobs = (delayed(fn)(item) for item in items)
    kwargs: dict[str, Any] = {"n_jobs": max_workers, "batch_size": chunksize}
    if method == "imap_unordered":
        kwargs["return_as"] = "generator_unordered"
    if timeout is not None:
        kwargs["timeout"] = timeout
    with Parallel(**kwargs) as parallel:
        return list(parallel(jobs))


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
    items = list(items)
    if not items:
        return []
    _validate(backend, method, chunksize, items)
    takes_arg_tuples = method in _TUPLE_ARG_METHODS
    max_workers = _resolve_max_workers(max_workers, len(items))
    if max_workers == 1:
        if takes_arg_tuples:
            return [fn(*args) for args in items]
        return [fn(item) for item in items]
    if backend in _MP_BACKENDS:
        return _run_mp(fn, items, method, backend, max_workers, chunksize, timeout)
    if backend in _CF_BACKENDS:
        kind = "thread" if backend == "cf_thread" else "process"
        return _run_futures(fn, items, method, kind, max_workers, chunksize, timeout)
    if backend == "joblib":
        return _run_joblib(fn, items, method, max_workers, chunksize, timeout)
    msg = f"unhandled backend: {backend!r}"
    raise AssertionError(msg)
