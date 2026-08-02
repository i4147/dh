from collections.abc import Callable, Iterable
from multiprocessing import get_context
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from .const import MAX_WORKERS

P = ParamSpec("P")
T = TypeVar("T")
R = TypeVar("R")


def mpf3(process_function: Callable, files: list[Path], **kwargs):
    from joblib import Parallel, delayed

    file_strings = [str(f) for f in files]
    return Parallel(n_jobs=-1)(delayed(process_function)(file_str, **kwargs) for file_str in file_strings)


def mpf_map(func: Callable, items: Iterable[Any]) -> list:
    with get_context(CONTEXT_METHOD).Pool(MAX_WORKERS) as p:
        return p.map(func, items)


def mpf_async(func: Callable[[Any], Any], items: Iterable[Any]):
    with get_context("spawn").Pool(MAX_WORKERS) as p:
        async_results = [p.apply_async(func, (item,)) for item in items]
        results = []
        for i, async_result in enumerate(async_results):
            try:
                results.append(async_result.get(timeout=30))
            except Exception as e:
                print(f"Item {i} failed: {e}")
                results.append(None)
        return results


def mpf[T, R](func: Callable[[T], R], items: Iterable[T]) -> list[R]:
    items_list = list(items)
    args = [(item,) for item in items_list]
    with get_context("spawn").Pool(16) as pool:
        return pool.starmap(func, args)


def mpf_starmap2(func: Callable[[Any], Any], items: Iterable[Any]):
    args = [(f,) for f in items]
    with get_context("spawn").Pool(MAX_WORKERS) as p:
        return p.starmap(func, args)


def mpf_starmap3(func: Callable, item_tuples: Iterable[tuple]) -> list:
    with get_context("spawn").Pool(MAX_WORKERS) as p:
        return p.starmap(func, item_tuples)


def mpf_imap(func: Callable[[Any], Any], items: Iterable[Any]):
    with get_context("spawn").Pool(MAX_WORKERS) as p:
        chunksize = max(1, len(list(items)) // (MAX_WORKERS * 4)) if items else 1
        return list(p.imap_unordered(func, items, chunksize=chunksize))


def mpf_imap2(func: Callable[[Any], Any], items: Iterable[Any]):
    with get_context("spawn").Pool(MAX_WORKERS) as p:
        results = []
        for result in p.imap_unordered(func, items):
            results.append(result)
        return results


def mpf_imap3(func: Callable[[Any], Any], items: Iterable[Any]):
    with get_context("spawn").Pool(MAX_WORKERS) as p:
        yield from p.imap_unordered(func, items)
