#!/usr/bin/env python3
"""Benchmark :func:`dh.mpf` across backends and workload shapes.

Every "case" runs the same worker over the same items through a different
backend. We report the *best* wall time over ``--repeats`` trials (best-of-N
is far more stable than mean when the OS scheduler and CPU frequency are
noisy), the speedup vs. a serial baseline, and a correctness check.

Usage
-----
    python -m dh.benchmark                  # default: all workloads
    python -m dh.benchmark --items 256
    python -m dh.benchmark --workload io
    python -m dh.benchmark --repeats 5
    python -m dh.benchmark --no-joblib      # skip the optional backend

Interpretation
--------------
* ``cpu``    — real Python bytecode in each item → ``ProcessPool*`` wins,
  ``thread_pool`` collapses under the GIL.
* ``io``     — ``time.sleep`` dominated → ``thread_pool`` wins; process
  backends pay fork + IPC overhead for nothing.
* ``mixed``  — the realistic middle ground.

If ``serial`` (baseline) is faster than a parallel method, your workload is
too small to amortize the pool startup — bump ``--items``.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from collections.abc import Callable
from typing import Any

from dh import MAX_WORKERS, PoolMethod, mpf

# ---------------------------------------------------------------------------
# Workloads
# ---------------------------------------------------------------------------


def cpu_work(n: int, *, iters: int = 50_000) -> int:
    """CPU-bound LCG iteration — one item burns a few ms of pure Python."""
    x = n
    for _ in range(iters):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
    return x


def io_work(t: float) -> float:
    """I/O-bound stand-in: sleep and return the duration."""
    time.sleep(t)
    return t


def mixed_work(n: int, *, iters: int = 15_000, nap: float = 0.002) -> int:
    """A little CPU, a little waiting — the common real-world shape."""
    x = cpu_work(n, iters=iters)
    time.sleep(nap)
    return x


# name -> (worker, items_factory)
WORKLOADS: dict[str, tuple[Callable[..., Any], Callable[[int], list[Any]]]] = {
    "cpu": (cpu_work, lambda n: list(range(n))),
    "io": (io_work, lambda n: [0.005] * n),
    "mixed": (mixed_work, lambda n: list(range(n))),
}


# ---------------------------------------------------------------------------
# Case matrix
# ---------------------------------------------------------------------------

#: (display name, method, extra kwargs to mpf)
Case = tuple[str, "PoolMethod | None", dict[str, Any]]


def build_cases(include_joblib: bool) -> list[Case]:
    """Return the (name, method, kwargs) rows we benchmark."""
    cases: list[Case] = [
        ("map", PoolMethod.MAP, {}),
        ("map(cs=1)", PoolMethod.MAP, {"chunksize": 1}),
        ("map(cs=auto)", PoolMethod.MAP, {"chunksize": None}),
        ("imap", PoolMethod.IMAP, {}),
        ("imap_unordered", PoolMethod.IMAP_UNORDERED, {}),
        ("process_pool", PoolMethod.PROCESS_POOL, {}),
        ("pp+timeout", PoolMethod.PROCESS_POOL, {"timeout": 30.0}),
        ("pp+bounded", PoolMethod.PROCESS_POOL, {"max_pending": 16}),
        ("thread_pool", PoolMethod.THREAD_POOL, {}),
    ]
    if include_joblib:
        cases.append(("joblib", PoolMethod.JOBLIB, {}))
    return cases


# ---------------------------------------------------------------------------
# Core timing harness
# ---------------------------------------------------------------------------


def _call_factory(
    worker: Callable[..., Any],
    items: list[Any],
    method: PoolMethod | None,
    kwargs: dict[str, Any],
    workers: int,
) -> Callable[[], list[Any]]:
    """Return a zero-arg callable that performs one full run."""
    if method is None:
        return lambda: [worker(x) for x in items]
    return lambda: mpf(worker, items, method=method, workers=workers, **kwargs)


def time_case(
    worker: Callable[..., Any],
    items: list[Any],
    method: PoolMethod | None,
    kwargs: dict[str, Any],
    workers: int,
    repeats: int,
) -> tuple[float, list[Any]]:
    """Run the case ``repeats`` times; return (best_seconds, last_result)."""
    call = _call_factory(worker, items, method, kwargs, workers)
    best = math.inf
    last: list[Any] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        last = call()
        dt = time.perf_counter() - t0
        best = min(best, dt)
    return best, last


def _checksum(seq: list[Any]) -> Any:
    """Order-independent sum used as a correctness probe."""
    try:
        return sum(x for x in seq if x is not None)
    except TypeError:  # non-numeric results
        return len(seq)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _fmt_row(name: str, secs: float, speedup: float, ok: bool) -> str:
    tick = "✓" if ok else "✗"
    return f"{name:<16} {secs:>9.3f}s {speedup:>7.2f}x  {tick:>3}"


def run_workload(
    wl_name: str,
    items: list[Any],
    cases: list[Case],
    workers: int,
    repeats: int,
) -> None:
    worker, _ = WORKLOADS[wl_name]

    print(f"── workload: {wl_name}  ({len(items)} items, workers={workers}, repeats={repeats}) ──")

    # Baseline: plain serial loop, same worker, same items.
    baseline_secs, baseline_res = time_case(worker, items, None, {}, workers, repeats)
    baseline_sum = _checksum(baseline_res)

    header = f"{'case':<16} {'best':>10} {'speedup':>8}  {'ok':>3}"
    print(header)
    print("-" * len(header))
    print(_fmt_row("serial", baseline_secs, 1.0, True))

    for name, method, kwargs in cases:
        try:
            secs, res = time_case(worker, items, method, kwargs, workers, repeats)
        except Exception as exc:  # noqa: BLE001 — the whole point is to catch everything
            print(f"{name:<16} {'—':>10} {'—':>8}  ERR  {type(exc).__name__}: {exc}")
            continue

        speedup = baseline_secs / secs if secs > 0 else float("inf")
        ok = len(res) == len(items) and _checksum(res) == baseline_sum
        print(_fmt_row(name, secs, speedup, ok))

    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dh.benchmark",
        description="Benchmark dh.mpf across backends.",
    )
    parser.add_argument(
        "--items",
        type=int,
        default=64,
        help="number of work items per workload (default: 64)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="trials per case; best-of-N is reported (default: 3)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=MAX_WORKERS,
        help=f"worker count passed to mpf (default: {MAX_WORKERS})",
    )
    parser.add_argument(
        "--workload",
        choices=[*WORKLOADS, "all"],
        default="all",
        help="which workload(s) to run (default: all)",
    )
    parser.add_argument(
        "--no-joblib",
        action="store_true",
        help="skip the optional joblib backend even if it is installed",
    )
    args = parser.parse_args(argv)

    if args.items < 1:
        print("--items must be >= 1", file=sys.stderr)
        return 2
    if args.repeats < 1:
        print("--repeats must be >= 1", file=sys.stderr)
        return 2

    have_joblib = False
    if not args.no_joblib:
        try:
            import joblib  # noqa: F401

            have_joblib = True
        except ImportError:
            have_joblib = False

    workloads = list(WORKLOADS) if args.workload == "all" else [args.workload]
    cases = build_cases(have_joblib)

    print(
        f"dh.mpf benchmark — "
        f"workers={args.workers}, items={args.items}, "
        f"repeats={args.repeats}, joblib={'yes' if have_joblib else 'no'}"
    )
    print()

    for wl_name in workloads:
        _, make_items = WORKLOADS[wl_name]
        items = make_items(args.items)
        run_workload(wl_name, items, cases, args.workers, args.repeats)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
