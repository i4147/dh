from typing import Literal
from _typeshed import Incomplete

from __future__ import annotations
import multiprocessing
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Executor, Future, ProcessPoolExecutor, ThreadPoolExecutor, wait
from dataclasses import dataclass
from multiprocessing import Pool, get_context
from pathlib import Path
from typing import Any, TypeVar

MAX_WORKERS: Literal[8] = 8


def mpf_async(func: Callable, files: Iterable[Path], workers: int = ..., timeout: int = 30) -> list[Any]: ...


def mpf_map(func: Callable, files: Iterable[Path], workers: int = ...) -> list[Any]: ...


def mpf_imap(func: Callable, files: Iterable[Path], workers: int = ..., timeout: int = 30, chunksize: int = 1) -> list[Any]: ...


def mpf_imapu(func: Callable, files: Iterable[Path], workers: int = ..., chunksize: int = 1) -> list[Any]: ...


def mpf_starmap(func: Callable, files: Iterable[Path], extra_args: list[tuple] | None = None, workers: int = ...) -> list[Any]: ...


def mpf_ppe(func: Callable, files: Iterable[Path], workers: int = ..., timeout: int = 30) -> list[Any]: ...


def mpf_ppe_ac(func: Callable, files: Iterable[Path], workers: int = ..., timeout: int = 30) -> list[Any]: ...


def mpf_tpe(func: Callable, files: Iterable[Path], workers: int = ..., timeout: int = 30) -> list[Any]: ...


T = TypeVar("T")

R = TypeVar("R")


@dataclass
class ParallelSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0

    def __init__(self, total: int = ..., succeeded: int = ..., failed: int = ...) -> None: ...


def mpf3[T, R](func: Callable[[T], tuple[R, str | None]], items: Iterable[T], *, max_workers: int = ..., max_pending_factor: int = 8, on_success: Callable[[T, R], None] | None = None, on_error: Callable[[T, str], None] | None = None, executor_factory: Callable[[int], Executor] | None = None) -> ParallelSummary: ...


def mpf(worker_fn: Callable, items: list[Any], num_jobs: int = 1, *worker_args: Incomplete, **worker_kwargs: Incomplete) -> list[Any]: ...


def mpf2(worker_fn: Callable, items: list[Any], num_jobs: int = 1, *worker_args: Incomplete, **worker_kwargs: Incomplete) -> list[Any]: ...


def mpf_joblib(process_function: Callable, files: list[Path], **kwargs: Incomplete) -> Incomplete: ...
