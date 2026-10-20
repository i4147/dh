from __future__ import annotations
import argparse
from collections.abc import Callable
from dataclasses import asdict, dataclass
import hashlib
import json
import multiprocessing as mp
import os
import platform
import statistics
import sys
import time
from typing import Any

from jobutils import PoolMethod, mpf


def cpu_task(n: int) -> int:
    data = b"x" * 64
    for _ in range(n):
        data = hashlib.sha256(data).digest()
    return data[0]


def io_task(seconds: float) -> float:
    time.sleep(seconds)
    return seconds


def tiny_task(x: int) -> int:
    return x + 1


@dataclass(frozen=True)
class Scenario:
    name: str
    func: Callable[[Any], Any]
    make_items: Callable[[int], list[Any]]
    default_items: int
    methods: tuple[str, ...]


@dataclass
class Result:
    scenario: str
    method: str
    workers: int
    chunksize: int | None
    items: int
    repeat: int
    median_s: float
    min_s: float
    stdev_s: float
    items_per_s: float
    speedup: float | None = None


SCENARIOS: dict[str, Scenario] = {
    "cpu": Scenario(
        "cpu",
        cpu_task,
        lambda n: [20000] * n,
        256,
        ("serial", "map", "imap", "imap_unordered", "process_pool", "thread_pool", "joblib"),
    ),
    "io": Scenario(
        "io",
        io_task,
        lambda n: [0.01] * n,
        200,
        ("serial", "imap_unordered", "process_pool", "thread_pool", "joblib"),
    ),
    "tiny": Scenario(
        "tiny",
        tiny_task,
        lambda n: list(range(n)),
        20000,
        ("serial", "map", "imap_unordered", "process_pool", "thread_pool", "joblib"),
    ),
}


def joblib_available() -> bool:
    try:
        import joblib  # noqa: F401
    except ImportError:
        return False
    return True


def time_call(fn: Callable[[], Any], repeat: int, warmup: int) -> list[float]:
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return samples


def summarize(
    scenario: str, method: str, workers: int, chunksize: int | None, items: int, samples: list[float]
) -> Result:
    median = statistics.median(samples)
    return Result(
        scenario=scenario,
        method=method,
        workers=workers,
        chunksize=chunksize,
        items=items,
        repeat=len(samples),
        median_s=median,
        min_s=min(samples),
        stdev_s=statistics.stdev(samples) if len(samples) > 1 else 0.0,
        items_per_s=items / median if median > 0 else float("inf"),
    )


def bench_mpf(
    scenario: Scenario, method: str, items: list[Any], workers: int, chunksize: int | None, repeat: int, warmup: int
) -> Result:
    def run() -> Any:
        return mpf(scenario.func, items, method, workers=workers, chunksize=chunksize)

    return summarize(scenario.name, method, workers, chunksize, len(items), time_call(run, repeat, warmup))


def bench_raw_pool(
    scenario: Scenario, items: list[Any], workers: int, chunksize: int | None, repeat: int, warmup: int
) -> Result:
    def run() -> Any:
        with mp.get_context().Pool(workers) as pool:
            return list(pool.imap_unordered(scenario.func, items, chunksize or 1))

    return summarize(
        scenario.name, "raw_imap_unordered", workers, chunksize, len(items), time_call(run, repeat, warmup)
    )


def verify_correct(scenario: Scenario, items: list[Any], methods: list[str], workers: int) -> None:
    expected = [scenario.func(x) for x in items[: min(len(items), 16)]]
    probe = items[: min(len(items), 16)]
    for m in methods:
        got = mpf(scenario.func, probe, m, workers=min(workers, 2))
        if sorted(map(repr, got)) != sorted(map(repr, expected)):
            raise AssertionError(f"{scenario.name}/{m} produced wrong results")


def add_speedups(results: list[Result]) -> None:
    baselines = {r.scenario: r.median_s for r in results if r.method == "serial"}
    for r in results:
        base = baselines.get(r.scenario)
        if base and r.median_s > 0:
            r.speedup = base / r.median_s


def format_table(results: list[Result]) -> str:
    header = ("scenario", "method", "workers", "chunk", "items", "median s", "min s", "stdev s", "items/s", "speedup")
    rows = [header]
    for r in results:
        rows.append((
            r.scenario,
            r.method,
            str(r.workers),
            "-" if r.chunksize is None else str(r.chunksize),
            str(r.items),
            f"{r.median_s:.6f}",
            f"{r.min_s:.6f}",
            f"{r.stdev_s:.6f}",
            f"{r.items_per_s:,.0f}",
            "-" if r.speedup is None else f"{r.speedup:.2f}x",
        ))
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    lines = []
    for n, row in enumerate(rows):
        lines.append("  ".join(cell.ljust(widths[i]) if i < 2 else cell.rjust(widths[i]) for i, cell in enumerate(row)))
        if n == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def run_methods(args: argparse.Namespace) -> list[Result]:
    results: list[Result] = []
    has_joblib = joblib_available()
    for name in args.scenarios:
        scenario = SCENARIOS[name]
        n = args.items or scenario.default_items
        items = scenario.make_items(n)
        methods = [m for m in (args.methods or scenario.methods) if m != "joblib" or has_joblib]
        if args.verify:
            verify_correct(scenario, items, methods, args.workers)
        print(f"[{name}] {n} items, workers={args.workers}", file=sys.stderr)
        for method in methods:
            workers = 1 if method == "serial" else args.workers
            res = bench_mpf(scenario, method, items, workers, args.chunksize, args.repeat, args.warmup)
            results.append(res)
            print(f"  {method:<16} {res.median_s:.4f}s", file=sys.stderr)
        if args.raw_baseline:
            res = bench_raw_pool(scenario, items, args.workers, args.chunksize, args.repeat, args.warmup)
            results.append(res)
            print(f"  {res.method:<16} {res.median_s:.4f}s", file=sys.stderr)
    return results


def run_chunk_sweep(args: argparse.Namespace) -> list[Result]:
    results: list[Result] = []
    scenario = SCENARIOS[args.sweep_scenario]
    n = args.items or scenario.default_items
    items = scenario.make_items(n)
    print(f"[chunk sweep: {scenario.name}] {n} items, workers={args.workers}", file=sys.stderr)
    for chunk in args.sweep_chunks:
        res = bench_mpf(scenario, "imap_unordered", items, args.workers, chunk, args.repeat, args.warmup)
        res.scenario = f"{scenario.name}/chunk"
        results.append(res)
        print(f"  chunk={chunk:<6} {res.median_s:.4f}s", file=sys.stderr)
    return results


def run_worker_scaling(args: argparse.Namespace) -> list[Result]:
    results: list[Result] = []
    scenario = SCENARIOS[args.scaling_scenario]
    n = args.items or scenario.default_items
    items = scenario.make_items(n)
    print(f"[worker scaling: {scenario.name}] {n} items", file=sys.stderr)
    for w in args.scaling_workers:
        res = bench_mpf(scenario, "process_pool", items, w, args.chunksize, args.repeat, args.warmup)
        res.scenario = f"{scenario.name}/scaling"
        results.append(res)
        print(f"  workers={w:<4} {res.median_s:.4f}s", file=sys.stderr)
    return results


def run_feature_overhead(args: argparse.Namespace) -> list[Result]:
    results: list[Result] = []
    scenario = SCENARIOS["tiny"]
    n = args.items or scenario.default_items
    items = scenario.make_items(n)
    variants: dict[str, dict[str, Any]] = {
        "plain": {},
        "retries=2": {"retries": 2},
        "return_exceptions": {"return_exceptions": True},
        "ordered": {"ordered": True},
        "on_progress": {"on_progress": lambda i, v: None},
    }
    print(f"[feature overhead: imap_unordered/{scenario.name}] {n} items", file=sys.stderr)
    for label, extra in variants.items():

        def run(extra: dict[str, Any] = extra) -> Any:
            return mpf(scenario.func, items, "imap_unordered", workers=args.workers, chunksize=args.chunksize, **extra)

        res = summarize("overhead", label, args.workers, args.chunksize, n, time_call(run, args.repeat, args.warmup))
        results.append(res)
        print(f"  {label:<18} {res.median_s:.4f}s", file=sys.stderr)
    base = next(r.median_s for r in results if r.method == "plain")
    for r in results:
        r.speedup = base / r.median_s if r.median_s > 0 else None
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark jobutils.mpf backends")
    p.add_argument("--scenarios", nargs="+", choices=sorted(SCENARIOS), default=["cpu", "io", "tiny"])
    p.add_argument("--methods", nargs="+", default=None, help="restrict to these PoolMethod values")
    p.add_argument("--items", type=int, default=0, help="override item count for every scenario")
    p.add_argument("--workers", type=int, default=min(os.cpu_count() or 1, 8))
    p.add_argument("--chunksize", type=int, default=4)
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--raw-baseline", action="store_true", help="also time a bare multiprocessing.Pool")
    p.add_argument("--chunk-sweep", action="store_true")
    p.add_argument("--sweep-scenario", choices=sorted(SCENARIOS), default="tiny")
    p.add_argument("--sweep-chunks", nargs="+", type=int, default=[1, 2, 4, 8, 16, 64, 256])
    p.add_argument("--worker-scaling", action="store_true")
    p.add_argument("--scaling-scenario", choices=sorted(SCENARIOS), default="cpu")
    p.add_argument("--scaling-workers", nargs="+", type=int, default=[1, 2, 4, 8])
    p.add_argument("--feature-overhead", action="store_true")
    p.add_argument("--no-verify", dest="verify", action="store_false")
    p.add_argument("--json", type=str, default=None, help="write results to this JSON file")
    args = p.parse_args(argv)
    if args.methods:
        args.methods = [PoolMethod.parse(m).value for m in args.methods]
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print(
        f"python {platform.python_version()} on {platform.system()} {platform.machine()}, "
        f"cpus={os.cpu_count()}, start_method={mp.get_start_method()}",
        file=sys.stderr,
    )
    groups: list[tuple[str, list[Result]]] = [("methods", run_methods(args))]
    add_speedups(groups[0][1])
    if args.chunk_sweep:
        groups.append(("chunk sweep", run_chunk_sweep(args)))
    if args.worker_scaling:
        sweep = run_worker_scaling(args)
        base = next((r.median_s for r in sweep if r.workers == min(args.scaling_workers)), None)
        for r in sweep:
            r.speedup = base / r.median_s if base and r.median_s > 0 else None
        groups.append(("worker scaling", sweep))
    if args.feature_overhead:
        groups.append(("feature overhead (speedup = plain / variant)", run_feature_overhead(args)))
    for title, rows in groups:
        print(f"\n== {title} ==")
        print(format_table(rows))
    if args.json:
        payload = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpus": os.cpu_count(),
            "groups": {title: [asdict(r) for r in rows] for title, rows in groups},
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
