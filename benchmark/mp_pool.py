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
    return func(*item)


def run_pool[T](
    func: Callable[..., T],
    items: Sequence[Any],
    method: PoolMethod = "map",
    *,
    star: bool = False,
    workers: int = POOL_WORKERS,
) -> list[T]:
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
    parser.add_argument(
        "--pool-method",
        choices=POOL_METHODS,
        default="map",
        help="Multiprocessing pool method used for parallelism (default: map).",
    )
