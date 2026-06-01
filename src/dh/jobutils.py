from collections import deque
from collections.abc import Callable, Iterable
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Union

CHUNK_SIZE = 32768
MAX_WORKERS: int = 4
CONTEXT_METHOD: str = "spawn"


def mpf(process_function: Callable, files: list[Path], **kwargs):
    from joblib import Parallel, delayed

    return Parallel(n_jobs=-1)((delayed(process_function)(file, **kwargs) for file in files))


def mpf2(
    processing_function: Callable, files: list[str], chunk_size: int = 500, n_jobs: int = -1, **kwargs
) -> list[Any]:
    from joblib import Parallel, delayed

    all_results = []
    total_files = len(files)
    num_chunks = (total_files + chunk_size - 1) // chunk_size
    for i in range(num_chunks):
        start_index = i * chunk_size
        end_index = min((i + 1) * chunk_size, total_files)
        file_chunk = files[start_index:end_index]
        delayed_tasks = [delayed(processing_function)(file, **kwargs) for file in file_chunk]
        chunk_results = Parallel(n_jobs=n_jobs)(delayed_tasks)
        all_results.extend(chunk_results)
    return all_results


def mpf3(func: Callable[[Any], Any], items: Iterable[Any]):
    args = [(f,) for f in items]
    with get_context("spawn").Pool(4) as p:
        return p.starmap(func, args)


def mpf4(
    func: Callable[[Any], Any], items: Iterable[Any], max_in_flight: int = 4, num_processes: int = 4
) -> list[Union[Any, Exception]]:
    with get_context(CONTEXT_METHOD).Pool(processes=num_processes) as p:
        results_list: list[Union[Any, Exception]] = [None] * len(list(items))
        indexed_items = list(enumerate(items))
        pending_results = deque()
        task_iterator = iter(indexed_items)
        try:
            while True:
                while len(pending_results) < max_in_flight:
                    try:
                        original_index, item = next(task_iterator)
                        async_result = p.apply_async(func, (item,))
                        pending_results.append((original_index, async_result))
                    except StopIteration:
                        break
                    except Exception as e:
                        results_list[original_index] = e
                if not pending_results and len(results_list) == len(indexed_items):
                    break
                process_a_result = len(pending_results) >= max_in_flight or len(pending_results) > 0
                if process_a_result and pending_results:
                    try:
                        original_index, async_result = pending_results.popleft()
                        result = async_result.get()
                        results_list[original_index] = result
                    except Exception as e:
                        results_list[original_index] = e
                elif not pending_results and len(results_list) == len(indexed_items):
                    break
        except Exception as e:
            msg = "error"
            raise Exception(msg)
    return results_list


def mpf5(
    processing_function: Callable, files: list[str], chunk_size: int = 500, n_jobs: int = -1, **kwargs
) -> list[Any]:
    from joblib import Parallel, delayed

    all_results = []
    total_files = len(files)
    num_chunks = (total_files + chunk_size - 1) // chunk_size
    for i in range(num_chunks):
        start_index = i * chunk_size
        end_index = min((i + 1) * chunk_size, total_files)
        file_chunk = files[start_index:end_index]
        total = len(file_chunk)
        delayed_tasks = []
        for file in file_chunk:

            def wrapped_processing_function(f, **kw):
                return processing_function(f, **kw)

            delayed_tasks.append(delayed(wrapped_processing_function)(file, **kwargs))
            chunk_results = Parallel(n_jobs=n_jobs)(delayed_tasks)
        all_results.extend(chunk_results)
    return all_results


def mpf6(
    func: Callable[[Any], Any], items: Iterable[Any], max_in_flight: int = 4, num_processes: int = 4
) -> list[Union[Any, Exception]]:
    with get_context(CONTEXT_METHOD).Pool(processes=num_processes) as p:
        results_list: list[Union[Any, Exception]] = [None] * len(list(items))
        indexed_items = list(enumerate(items))
        pending_results = deque()
        task_iterator = iter(indexed_items)
        try:
            while True:
                while len(pending_results) < max_in_flight:
                    try:
                        original_index, item = next(task_iterator)
                        async_result = p.apply_async(func, (item,))
                        pending_results.append((original_index, async_result))
                    except StopIteration:
                        break
                    except Exception as e:
                        results_list[original_index] = e
                if (
                    not pending_results
                    and len(results_list) == len(indexed_items)
                    and all((r is not None for r in results_list))
                ):
                    break
                if len(pending_results) == 0 and len(results_list) == len(indexed_items):
                    break
                process_a_result = len(pending_results) >= max_in_flight or (
                    len(pending_results) > 0 and next(task_iterator, None) is None
                )
                if process_a_result and len(pending_results) > 0 and (next(task_iterator, None) is None):
                    task_iterator = iter(indexed_items)
                if process_a_result and pending_results:
                    try:
                        original_index, async_result = pending_results.popleft()
                        result = async_result.get()
                        results_list[original_index] = result
                    except Exception as e:
                        results_list[original_index] = e
                    if not pending_results and len(results_list) == len(indexed_items):
                        break
                elif not pending_results and len(results_list) == len(indexed_items):
                    break
                elif not pending_results and len(results_list) != len(indexed_items):
                    pass
        except Exception as e:
            msg = "error"
            raise Exception(msg)
    return results_list
