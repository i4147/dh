#!/usr/bin/env python3
"""
Benchmark parallel file-hashing strategies.

Usage:
    python bench_mpf.py <folder> [--repeat N] [--pattern GLOB] [--pool SIZE]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import statistics
import sys
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from multiprocessing import Pool
from multiprocessing.pool import AsyncResult
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")

CHUNK = 1 << 20  # 1 MiB read buffer


# ---------------------------------------------------------------------------
# Implementations under test
# ---------------------------------------------------------------------------
def mpf_as[T, R](func: Callable[[T], R], files: Iterable[T]) -> list[R]:
    results: list[R] = []
    with Pool(8) as pool:
        pending: deque = deque()
        for f in files:
            pending.append(pool.apply_async(func, (f,)))
            if len(pending) > 32:
                results.append(pending.popleft().get())
        while pending:
            results.append(pending.popleft().get())
    return results


def mpf_bounded[T, R](
    func: Callable[[T], R],
    files: Iterable[T],
    *,
    processes: int | None = None,
    max_inflight: int | None = None,
) -> list[R]:
    processes = processes or os.cpu_count() or 1
    max_inflight = max_inflight or 2 * processes
    results: list[R] = []
    with Pool(processes) as pool:
        pending: deque[AsyncResult[R]] = deque()
        for f in files:
            if len(pending) >= max_inflight:
                results.append(pending.popleft().get())
            pending.append(pool.apply_async(func, (f,)))
        while pending:
            results.append(pending.popleft().get())
    return results


def mpf_stream[T, R](
    func: Callable[[T], R],
    files: Iterable[T],
    *,
    processes: int | None = None,
    chunksize: int = 1,
) -> Iterator[R]:
    processes = processes or os.cpu_count() or 1
    with Pool(processes) as pool:
        yield from pool.imap(func, files, chunksize=chunksize)


def mpf_imap2[T, R](
    func: Callable[[T], R],
    files: Iterable[T],
    *,
    processes: int | None = None,
    chunksize: int = 1,
) -> list[R]:
    processes = processes or os.cpu_count() or 1
    with Pool(processes) as pool:
        return list(pool.imap(func, files, chunksize=chunksize))


# ---------------------------------------------------------------------------
# Workload
# ---------------------------------------------------------------------------
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def collect_files(folder: str, pattern: str = "*") -> list[str]:
    root = Path(folder)
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {folder}")
    files = [str(p) for p in root.rglob(pattern) if p.is_file()]
    if not files:
        raise SystemExit(f"No files matched {pattern!r} under {folder}")
    return files


# ---------------------------------------------------------------------------
# Benchmark harness
# ---------------------------------------------------------------------------
def time_once(fn: Callable[[], object]) -> float:
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def bench(
    name: str,
    fn: Callable[[], object],
    *,
    repeat: int,
    warmup: int = 1,
) -> dict[str, float]:
    for _ in range(warmup):
        fn()
    times = [time_once(fn) for _ in range(repeat)]
    return {
        "name": name,
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "min": min(times),
        "max": max(times),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", help="folder to hash")
    ap.add_argument("--repeat", type=int, default=3, help="timed repetitions per function (default: 3)")
    ap.add_argument("--warmup", type=int, default=1, help="warmup runs per function (default: 1)")
    ap.add_argument("--pattern", default="*", help="glob pattern for files (default: *)")
    ap.add_argument("--pool", type=int, default=os.cpu_count() or 1, help="worker count for the parametrized variants")
    args = ap.parse_args()

    files = collect_files(args.folder, args.pattern)
    total_bytes = sum(os.path.getsize(f) for f in files)
    print(f"Folder      : {args.folder}")
    print(f"Files       : {len(files)}")
    print(f"Total size  : {total_bytes / 1e6:.2f} MB")
    print(f"CPUs        : {os.cpu_count()}  (pool size for parametrized: {args.pool})")
    print(f"Repeat      : {args.repeat}  Warmup: {args.warmup}")
    print("-" * 72)

    # Sanity: all implementations should produce the same digests, in order.
    expected = [sha256_file(f) for f in files[: min(50, len(files))]]
    checks = {
        "mpf_as": mpf_as(sha256_file, files),
        "mpf_bounded": mpf_bounded(sha256_file, files, processes=args.pool),
        "mpf_stream": list(mpf_stream(sha256_file, files, processes=args.pool)),
        "mpf_imap2": mpf_imap2(sha256_file, files, processes=args.pool),
    }
    for name, got in checks.items():
        if got != checks["mpf_as"]:
            print(f"!! {name} produced different results from mpf_as")
            return 1

    variants: list[tuple[str, Callable[[], object]]] = [
        ("mpf_as (Pool(8), cap=32)", lambda: mpf_as(sha256_file, files)),
        (f"mpf_bounded (p={args.pool})", lambda: mpf_bounded(sha256_file, files, processes=args.pool)),
        (f"mpf_stream (p={args.pool}, cs=1)", lambda: list(mpf_stream(sha256_file, files, processes=args.pool))),
        (f"mpf_imap2 (p={args.pool}, cs=1)", lambda: mpf_imap2(sha256_file, files, processes=args.pool)),
        (f"mpf_imap2 (p={args.pool}, cs=8)", lambda: mpf_imap2(sha256_file, files, processes=args.pool, chunksize=8)),
        (f"mpf_imap2 (p={args.pool}, cs=32)", lambda: mpf_imap2(sha256_file, files, processes=args.pool, chunksize=32)),
        ("serial baseline", lambda: [sha256_file(f) for f in files]),
    ]

    rows = []
    for name, fn in variants:
        stats = bench(name, fn, repeat=args.repeat, warmup=args.warmup)
        rows.append(stats)
        print(
            f"{name:<36} "
            f"mean={stats['mean'] * 1000:8.1f}ms  "
            f"median={stats['median'] * 1000:8.1f}ms  "
            f"min={stats['min'] * 1000:8.1f}ms  "
            f"max={stats['max'] * 1000:8.1f}ms"
        )

    # Rank by median (more robust than mean to GC/scheduler noise).
    rows.sort(key=lambda r: r["median"])
    print("-" * 72)
    print("Ranking (by median):")
    for i, r in enumerate(rows, 1):
        print(f"  {i}. {r['name']:<36} median={r['median'] * 1000:8.1f}ms")

    serial = next(r for r in rows if r["name"] == "serial baseline")
    print("-" * 72)
    print(f"Fastest: {rows[0]['name']}")
    print(f"Speedup vs serial: {serial['median'] / rows[0]['median']:.2f}x")
    return 0


if __name__ == "__main__":
    sys.exit(main())
