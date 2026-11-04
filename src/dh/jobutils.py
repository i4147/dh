from collections.abc import Callable, Iterable, Iterator, Sequence
import concurrent.futures as cf
import contextlib
from dataclasses import dataclass
from enum import StrEnum
from functools import partial
import importlib.util
import math
import multiprocessing as mp
from multiprocessing.pool import Pool as MpPool
import os
import pickle
import queue
import signal
import time
import traceback
from typing import Any, Literal, Protocol, cast

from loguru import logger


__all__ = [
    "Method",
    "MethodUnavailableError",
    "MpfError",
    "Outcome",
    "TaskError",
    "failures",
    "mpf",
    "values",
]
type ProgressKind = Literal["tqdm", "rich"]
type StartMethod = Literal["fork", "forkserver", "spawn"]
type ErrorMode = Literal["collect", "raise"]
type Packed = tuple[int, Any]
type Chunk = Sequence[Packed]


class MpfError(Exception):
    pass


class MethodUnavailableError(MpfError, RuntimeError):
    pass


class TaskError(MpfError):
    def __init__(self, outcome: Outcome[Any, Any]) -> None:
        super().__init__(f"{outcome.item!r}: {outcome.error}")
        self.outcome = outcome


class Method(StrEnum):
    JOBLIB = "joblib"
    INTERPRETER = "interpreter"
    PROCESS = "process"
    THREAD = "thread"
    MAP = "map"
    IMAP = "imap"
    IMAP_UNORDERED = "imap_unordered"
    STARMAP = "starmap"
    APPLY_ASYNC = "apply_async"
    MAP_ASYNC = "map_async"
    STARMAP_ASYNC = "starmap_async"

    @classmethod
    def parse(cls, value: Method | str) -> Method:
        if isinstance(value, cls):
            return value
        key = value.strip().lower().replace("-", "_").replace(" ", "_")
        for prefix in ("concurrent.futures.", "multiprocessing.pool.", "mp.pool.", "cf.", "mp."):
            key = key.removeprefix(prefix)
        for suffix in ("_pool_executor", "poolexecutor", "_executor", "executor", "_pool", "pool"):
            key = key.removesuffix(suffix)
        try:
            return cls(key)
        except ValueError:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"unknown method {value!r}; choose from: {choices}") from None


STAR_METHODS: frozenset[Method] = frozenset({Method.STARMAP, Method.STARMAP_ASYNC})
EXECUTOR_METHODS: frozenset[Method] = frozenset({Method.PROCESS, Method.THREAD, Method.INTERPRETER})
UNPICKLED_METHODS: frozenset[Method] = frozenset({Method.THREAD, Method.JOBLIB})


@dataclass(frozen=True, slots=True)
class Outcome[T, R]:
    index: int
    item: T
    value: R | None = None
    error: str | None = None
    traceback: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


type AnyOutcome = Outcome[Any, Any]


def values[T, R](outcomes: Iterable[Outcome[T, R]]) -> list[R]:
    return [cast(R, outcome.value) for outcome in outcomes if outcome.ok]


def failures[T, R](outcomes: Iterable[Outcome[T, R]]) -> list[Outcome[T, R]]:
    return [outcome for outcome in outcomes if not outcome.ok]


@dataclass(frozen=True, slots=True)
class _Task:
    func: Callable[..., Any]
    star: bool = False

    def run(self, index: int, item: Any) -> AnyOutcome:
        try:
            value = self.func(*item) if self.star else self.func(item)
        except Exception as exc:
            return Outcome(
                index,
                item,
                error=f"{type(exc).__name__}: {exc}",
                traceback=traceback.format_exc(),
            )
        return Outcome(index, item, value=value)

    def __call__(self, packed: Packed) -> AnyOutcome:
        return self.run(*packed)


def _run_chunk(task: _Task, chunk: Chunk) -> list[AnyOutcome]:
    return [task.run(index, item) for index, item in chunk]


def _failed(chunk: Chunk, exc: BaseException) -> list[AnyOutcome]:
    message = f"{type(exc).__name__}: {exc}"
    return [Outcome(index, item, error=message) for index, item in chunk]


def _ignore_sigint() -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _cpu_count() -> int:
    counter = getattr(os, "process_cpu_count", os.cpu_count)
    return counter() or 1


def _resolve_workers(method: Method, requested: int | None, total: int) -> int:
    if requested is not None:
        if requested < 1:
            raise ValueError("workers must be >= 1")
        return min(requested, total)
    cpus = _cpu_count()
    default = min(32, cpus + 4) if method is Method.THREAD else cpus
    return max(1, min(default, total))


def _resolve_chunksize(method: Method, requested: int | None, total: int, workers: int) -> int:
    if requested is not None:
        if requested < 1:
            raise ValueError("chunksize must be >= 1")
        return requested
    if method in {Method.THREAD, Method.APPLY_ASYNC}:
        return 1
    return max(1, min(64, math.ceil(total / (workers * 4))))


def _check_available(method: Method) -> None:
    if method is Method.INTERPRETER and not hasattr(cf, "InterpreterPoolExecutor"):
        raise MethodUnavailableError("InterpreterPoolExecutor requires Python 3.14+")
    if method is Method.JOBLIB and importlib.util.find_spec("joblib") is None:
        raise MethodUnavailableError("joblib is not installed (pip install 'joblib>=1.4')")


def _check_picklable(task: _Task, method: Method) -> None:
    try:
        pickle.dumps(task)
    except Exception as exc:
        raise TypeError(
            f"{method.value}: {task.func!r} cannot be pickled ({exc}); "
            "use a module-level function, or the 'thread' / 'joblib' method"
        ) from exc


def _check_star_items(items: Sequence[Any]) -> None:
    for position, item in enumerate(items):
        if not isinstance(item, tuple | list):
            raise TypeError(f"starmap methods need tuple/list items, got {type(item).__name__} at position {position}")


def _run_joblib(task: _Task, packed: Sequence[Packed], workers: int, backend: str | None) -> Iterator[AnyOutcome]:
    from joblib import Parallel, delayed

    with Parallel(n_jobs=workers, backend=backend, return_as="generator_unordered") as parallel:
        yield from parallel(delayed(task)(item) for item in packed)


def _make_executor(method: Method, workers: int, mp_context: StartMethod | None) -> cf.Executor:
    match method:
        case Method.PROCESS:
            return cf.ProcessPoolExecutor(
                max_workers=workers,
                mp_context=mp.get_context(mp_context),
                initializer=_ignore_sigint,
            )
        case Method.THREAD:
            return cf.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mpf")
        case Method.INTERPRETER:
            factory = getattr(cf, "InterpreterPoolExecutor")
            return factory(max_workers=workers)
    raise AssertionError(f"not an executor method: {method}")


def _abort_executor(executor: cf.Executor) -> None:
    executor.shutdown(wait=False, cancel_futures=True)
    terminate = getattr(executor, "terminate_workers", None)
    if callable(terminate):
        with contextlib.suppress(Exception):
            terminate()


def _run_executor(
    method: Method,
    task: _Task,
    packed: Sequence[Packed],
    workers: int,
    chunksize: int,
    mp_context: StartMethod | None,
) -> Iterator[AnyOutcome]:
    executor = _make_executor(method, workers, mp_context)
    try:
        futures = {
            executor.submit(_run_chunk, task, chunk): chunk
            for chunk in (packed[start : start + chunksize] for start in range(0, len(packed), chunksize))
        }
        for future in cf.as_completed(futures):
            try:
                outcomes = future.result()
            except Exception as exc:
                outcomes = _failed(futures[future], exc)
            yield from outcomes
    except BaseException:
        _abort_executor(executor)
        raise
    else:
        executor.shutdown(wait=True)


def _on_apply_error(results: queue.SimpleQueue[AnyOutcome], index: int, item: Any, exc: BaseException) -> None:
    results.put(Outcome(index, item, error=f"{type(exc).__name__}: {exc}"))


def _apply_async(pool: MpPool, task: _Task, packed: Sequence[Packed]) -> Iterator[AnyOutcome]:
    results: queue.SimpleQueue[AnyOutcome] = queue.SimpleQueue()
    for index, item in packed:
        pool.apply_async(
            task.run,
            (index, item),
            callback=results.put,
            error_callback=partial(_on_apply_error, results, index, item),
        )
    for _ in range(len(packed)):
        yield results.get()


def _dispatch_pool(
    pool: MpPool, method: Method, task: _Task, packed: Sequence[Packed], chunksize: int
) -> Iterator[AnyOutcome]:
    match method:
        case Method.MAP:
            yield from pool.map(task, packed, chunksize)
        case Method.IMAP:
            yield from pool.imap(task, packed, chunksize)
        case Method.IMAP_UNORDERED:
            yield from pool.imap_unordered(task, packed, chunksize)
        case Method.STARMAP:
            yield from pool.starmap(task.run, packed, chunksize)
        case Method.MAP_ASYNC:
            yield from pool.map_async(task, packed, chunksize).get()
        case Method.STARMAP_ASYNC:
            yield from pool.starmap_async(task.run, packed, chunksize).get()
        case Method.APPLY_ASYNC:
            yield from _apply_async(pool, task, packed)
        case _:
            raise AssertionError(f"not a pool method: {method}")


def _run_pool(
    method: Method,
    task: _Task,
    packed: Sequence[Packed],
    workers: int,
    chunksize: int,
    mp_context: StartMethod | None,
) -> Iterator[AnyOutcome]:
    pool = mp.get_context(mp_context).Pool(processes=workers, initializer=_ignore_sigint)
    try:
        yield from _dispatch_pool(pool, method, task, packed, chunksize)
    except BaseException:
        pool.terminate()
        raise
    else:
        pool.close()
    finally:
        pool.join()


def _select_runner(
    method: Method,
    task: _Task,
    packed: Sequence[Packed],
    workers: int,
    chunksize: int,
    mp_context: StartMethod | None,
    backend: str | None,
) -> Iterator[AnyOutcome]:
    if method is Method.JOBLIB:
        return _run_joblib(task, packed, workers, backend)
    if method in EXECUTOR_METHODS:
        return _run_executor(method, task, packed, workers, chunksize, mp_context)
    return _run_pool(method, task, packed, workers, chunksize, mp_context)


class _Progress(Protocol):
    def advance(self, count: int = 1) -> None: ...
    def close(self) -> None: ...


class _NullProgress:
    def advance(self, count: int = 1) -> None:
        return None

    def close(self) -> None:
        return None


class _TqdmProgress:
    def __init__(self, total: int, description: str) -> None:
        from tqdm import tqdm

        self._bar = tqdm(total=total, desc=description, unit="item", dynamic_ncols=True)

    def advance(self, count: int = 1) -> None:
        self._bar.update(count)

    def close(self) -> None:
        self._bar.close()


class _RichProgress:
    def __init__(self, total: int, description: str) -> None:
        from rich.console import Console
        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            Progress,
            TextColumn,
            TimeElapsedColumn,
            TimeRemainingColumn,
        )

        self._progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=Console(stderr=True),
        )
        self._task = self._progress.add_task(description, total=total)
        self._progress.start()

    def advance(self, count: int = 1) -> None:
        self._progress.advance(self._task, count)

    def close(self) -> None:
        self._progress.stop()


def _make_progress(kind: ProgressKind | None, total: int, description: str) -> _Progress:
    if kind is None:
        return _NullProgress()
    try:
        if kind == "tqdm":
            return _TqdmProgress(total, description)
        return _RichProgress(total, description)
    except ImportError:
        logger.warning("progress backend {!r} is not installed; continuing without progress", kind)
        return _NullProgress()


def _log_failure(outcome: AnyOutcome) -> None:
    logger.error("{!r}: {}", outcome.item, outcome.error)
    if outcome.traceback:
        logger.debug("traceback for {!r}:\n{}", outcome.item, outcome.traceback)


def mpf[T, R](
    func: Callable[..., R],
    items: Iterable[T],
    method: Method | str = Method.IMAP_UNORDERED,
    *,
    workers: int | None = None,
    chunksize: int | None = None,
    progress: ProgressKind | None = None,
    ordered: bool = True,
    on_error: ErrorMode = "collect",
    mp_context: StartMethod | None = None,
    backend: str | None = None,
    description: str = "Processing",
) -> list[Outcome[T, R]]:
    chosen = Method.parse(method)
    if progress not in (None, "tqdm", "rich"):
        raise ValueError(f"progress must be None, 'tqdm' or 'rich', got {progress!r}")
    if on_error not in ("collect", "raise"):
        raise ValueError(f"on_error must be 'collect' or 'raise', got {on_error!r}")
    work = list(items)
    total = len(work)
    if total == 0:
        return []
    _check_available(chosen)
    if chosen in STAR_METHODS:
        _check_star_items(work)
    task = _Task(func, chosen in STAR_METHODS)
    if chosen not in UNPICKLED_METHODS:
        _check_picklable(task, chosen)
    count = _resolve_workers(chosen, workers, total)
    size = _resolve_chunksize(chosen, chunksize, total, count)
    packed: list[Packed] = list(enumerate(work))
    logger.debug("mpf start: method={} workers={} chunksize={} items={}", chosen.value, count, size, total)
    seen: dict[int, AnyOutcome] = {}
    started = time.perf_counter()
    bar = _make_progress(progress, total, description)
    runner = _select_runner(chosen, task, packed, count, size, mp_context, backend)
    try:
        with contextlib.closing(runner):
            for outcome in runner:
                seen[outcome.index] = outcome
                bar.advance()
                if not outcome.ok:
                    _log_failure(outcome)
                    if on_error == "raise":
                        raise TaskError(outcome)
    except TaskError:
        raise
    except KeyboardInterrupt:
        logger.warning("interrupted; workers were shut down")
        raise
    except Exception as exc:
        logger.error("{} aborted: {}: {}", chosen.value, type(exc).__name__, exc)
        if on_error == "raise":
            raise MpfError(f"{chosen.value} aborted: {exc}") from exc
        for index, item in packed:
            if index not in seen:
                seen[index] = Outcome(index, item, error=f"not completed: {type(exc).__name__}: {exc}")
                bar.advance()
    finally:
        bar.close()
    results = sorted(seen.values(), key=lambda outcome: outcome.index) if ordered else list(seen.values())
    failed = sum(1 for outcome in results if not outcome.ok)
    logger.info(
        "mpf done: method={} ok={} failed={} elapsed={:.2f}s workers={} chunksize={}",
        chosen.value,
        total - failed,
        failed,
        time.perf_counter() - started,
        count,
        size,
    )
    return cast(list[Outcome[T, R]], results)
