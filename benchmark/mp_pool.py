"""Reusable multiprocessing pool helper.
Provides a single entry point :func:`run_pool` that dispatches work across a fixed
8-worker ``multiprocessing.Pool`` using one of four strategies — ``map``,
``starmap``, ``imap_unordered``, or ``apply_async`` — selectable via the
``--pool-method`` CLI flag registered by :func:`add_pool_method_arg`.
Example
-------
    from mp_pool import add_pool_method_arg, run_pool
    def square(x: int) -> int:
        return x * x
    def add(a: int, b: int) -> int:
        return a + b
    results = run_pool(square, [1, 2, 3, 4])                       # map (single arg)
    results = run_pool(add, [(1, 2), (3, 4)], star=True)           # two args per item
    results = run_pool(add, [(1, 2), (3, 4)], method="starmap",
                       star=True)                                  # same, via starmap
"""
from __future__ import annotations
import argparse
from collections.abc import Callable, Sequence
from functools import partial
from multiprocessing.pool import AsyncResult, Pool
from typing import Any, Final, Literal, TypeVar
__all__ = [
    "POOL_METHODS",
    "POOL_WORKERS",
    "PoolMethod",
    "add_pool_method_arg",
    "run_pool",
]
POOL_WORKERS: Final[int] = 8
POOL_METHODS: Final[tuple[str, ...]] = (
    "map",
    "starmap",
    "imap_unordered",
    "apply_async",
)
PoolMethod = Literal["map", "starmap", "imap_unordered", "apply_async"]
T = TypeVar("T")
def _star_unpack[T](func: Callable[..., T], item: Sequence[Any]) -> T:
    """Unpack *item* as positional arguments for *func*.
    Defined at module level so :class:`functools.partial` over it stays picklable.
    """
    return func(*item)
def run_pool[T](
    func: Callable[..., T],
    items: Sequence[Any],
    method: PoolMethod = "map",
    *,
    star: bool = False,
    workers: int = POOL_WORKERS,
) -> list[T]:
    """Apply *func* to every element of *items* using a fixed-size multiprocessing pool.
    Parameters
    ----------
    func:
        Picklable callable (must be a module-level function, not a lambda).
    items:
        Sequence of arguments.  When ``star`` is ``True``, each item must itself be a
        sequence of positional arguments that is unpacked via ``func(*item)``.
    method:
        Dispatch strategy — one of ``"map"``, ``"starmap"``, ``"imap_unordered"``,
        ``"apply_async"``.
    star:
        Unpack each item as positional arguments (``func(*item)``).
    workers:
        Pool size; defaults to :data:`POOL_WORKERS` (8).
    Returns
    -------
    list[T]
        Results for every input item.  ``"imap_unordered"`` may return in any order.
    Raises
    ------
    ValueError
        If *method* is not one of :data:`POOL_METHODS`.
    """
    with Pool(processes=workers) as pool:
        if method == "map":
            if star:
                return pool.map(partial(_star_unpack, func), items)
            return pool.map(func, items)
        if method == "starmap":
            if star:
                return pool.starmap(func, items)
            return pool.starmap(func, [(item,) for item in items])
        if method == "imap_unordered":
            if star:
                return list(pool.imap_unordered(partial(_star_unpack, func), items))
            return list(pool.imap_unordered(func, items))
        if method == "apply_async":
            results: list[AsyncResult[T]]
            if star:
                results = [pool.apply_async(func, tuple(item)) for item in items]
            else:
                results = [pool.apply_async(func, (item,)) for item in items]
            return [r.get() for r in results]
    raise ValueError(f"Unsupported pool method: {method!r}")
def add_pool_method_arg(parser: argparse.ArgumentParser) -> None:
    """Register the standard ``--pool-method`` option on *parser*."""
    parser.add_argument(
        "--pool-method",
        choices=POOL_METHODS,
        default="map",
        help="Multiprocessing pool method used for parallelism (default: map).",
    )
