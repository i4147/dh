from __future__ import annotations
from collections.abc import Callable, Iterable, Iterator
from multiprocessing import get_context
from pathlib import Path
from typing import Any


MAX_WORKERS = 8
_MP_CONTEXT = get_context("spawn")


def _get_pool(workers: int = MAX_WORKERS):
    return _MP_CONTEXT.Pool(workers)


# fmt: off
def mpf3(process_function: Callable, files: list[Path], **kwargs: Any) -> list[Any]:
    from joblib import Parallel, delayed
    file_strings = [str(f) for f in files]
    return Parallel(n_jobs=MAX_WORKERS)(delayed(process_function)(file_str, **kwargs) for file_str in file_strings)
# fmt: on
def mpf_map(func: Callable, items: Iterable) -> list:
    items_list = list(items)
    if not items_list:
        return []
    with _get_pool() as p:
        return p.map(func, items_list)


def mpf_async(func: Callable, items: Iterable, timeout: int = 30) -> list:
    items_list = list(items)
    if not items_list:
        return []
    with _get_pool() as p:
        async_results = [p.apply_async(func, (item,)) for item in items_list]
        results = []
        for i, async_result in enumerate(async_results):
            try:
                results.append(async_result.get(timeout=timeout))
            except Exception as e:
                print(f"Item {i} failed: {e}")
                results.append(None)
        return results


def mpf(func: Callable, items: Iterable) -> list:
    items_list = list(items)
    if not items_list:
        return []
    args = [(item,) for item in items_list]
    with _get_pool(8) as pool:
        return pool.starmap(func, args)


def mpf_starmap2(func: Callable, items: Iterable) -> list:
    items_list = list(items)
    if not items_list:
        return []
    args = [(f,) for f in items_list]
    with _get_pool() as p:
        return p.starmap(func, args)


def mpf_starmap3(func: Callable, item_tuples: Iterable[tuple]) -> list:
    items_list = list(item_tuples)
    if not items_list:
        return []
    with _get_pool() as p:
        return p.starmap(func, items_list)


def mpf_imap(func: Callable, items: Iterable) -> list:
    items_list = list(items)
    if not items_list:
        return []
    chunksize = max(1, len(items_list) // (MAX_WORKERS * 4))
    with _get_pool() as p:
        return list(p.imap_unordered(func, items_list, chunksize=chunksize))


def mpf_imap2(func: Callable, items: Iterable) -> list:
    items_list = list(items)
    if not items_list:
        return []
    with _get_pool() as p:
        return list(p.imap_unordered(func, items_list))


def mpf_imap3(func: Callable, items: Iterable) -> Iterator:
    items_list = list(items)
    if not items_list:
        return
    with _get_pool() as p:
        yield from p.imap_unordered(func, items_list)


def run_parallel(func: Callable, files: Iterable[Path], workers: int = MAX_WORKERS, timeout: int = 30) -> list[Any]:
    files_list = list(files)
    if not files_list:
        return []
    with _get_pool(workers) as pool:
        async_results = [pool.apply_async(func, (file,)) for file in files_list]
        results = []
        for i, async_result in enumerate(async_results):
            try:
                results.append(async_result.get(timeout=timeout))
            except Exception as e:
                print(f"File {i} ({files_list[i]}) failed: {e}")
                results.append(None)
    return results
