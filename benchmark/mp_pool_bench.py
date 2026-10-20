from __future__ import annotations
import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
from statistics import mean
import time
from typing import Final, NamedTuple

from loguru import logger
from mp_pool import POOL_WORKERS, PoolMethod, run_pool
from xxhash import xxh64  # type: ignore[import-untyped]


DEFAULT_CHUNK_SIZE: Final[int] = 32768
HashRow = tuple[Path, str]


class BenchResult(NamedTuple):
    label: str
    runs: list[float]

    @property
    def best(self) -> float:
        return min(self.runs)

    @property
    def avg(self) -> float:
        return mean(self.runs)


def hash_file(path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> HashRow:
    h = xxh64()
    try:
        with path.open("rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
    except OSError as exc:
        logger.debug(f"Read error on {path}: {exc}")
        return (path, "")
    return (path, h.hexdigest())


def collect_files(root: Path, limit: int | None = None) -> list[Path]:
    files = [p for p in root.rglob("*") if p.is_file()]
    files.sort()
    if limit is not None:
        files = files[:limit]
    return files


def run_serial(files: Sequence[Path], chunk_size: int) -> list[HashRow]:
    return [hash_file(p, chunk_size) for p in files]


def _time_once(fn: Callable[[], Sequence[HashRow]]) -> tuple[list[HashRow], float]:
    start = time.perf_counter()
    result = list(fn())
    return result, time.perf_counter() - start


def _verify(label: str, expected: Sequence[HashRow], actual: Sequence[HashRow]) -> None:
    if sorted(expected, key=lambda r: str(r[0])) == sorted(actual, key=lambda r: str(r[0])):
        return
    logger.warning(f"{label}: results differ from serial baseline!")


def _strategies(files: Sequence[Path], chunk_size: int, workers: int) -> dict[str, Callable[[], list[HashRow]]]:
    star_tasks: list[tuple[Path, int]] = [(p, chunk_size) for p in files]

    def _map_single() -> list[HashRow]:
        return [hash_file(p, chunk_size) for p in files]

    strategies: dict[str, Callable[[], list[HashRow]]] = {}

    def _wrap(func: Callable[[Path], HashRow]) -> Callable[[Path], HashRow]:
        return func

    from functools import partial as _partial

    single_arg = _partial(hash_file, chunk_size=chunk_size)
    strategies["map (single-arg)"] = lambda: run_pool(single_arg, files, "map", workers=workers)
    strategies["imap_unordered (single-arg)"] = lambda: run_pool(single_arg, files, "imap_unordered", workers=workers)
    strategies["apply_async (single-arg)"] = lambda: run_pool(single_arg, files, "apply_async", workers=workers)
    strategies["starmap (star=True)"] = lambda: run_pool(hash_file, star_tasks, "starmap", star=True, workers=workers)
    strategies["map (star=True)"] = lambda: run_pool(hash_file, star_tasks, "map", star=True, workers=workers)
    strategies["imap_unordered (star=True)"] = lambda: run_pool(
        hash_file, star_tasks, "imap_unordered", star=True, workers=workers
    )
    strategies["apply_async (star=True)"] = lambda: run_pool(
        hash_file, star_tasks, "apply_async", star=True, workers=workers
    )
    _ = _map_single, _wrap
    return strategies


def benchmark(
    files: Sequence[Path],
    chunk_size: int,
    workers: int,
    runs: int,
) -> tuple[BenchResult, list[BenchResult]]:
    serial_times: list[float] = []
    expected: list[HashRow] = []
    for i in range(runs):
        result, elapsed = _time_once(lambda: run_serial(files, chunk_size))
        serial_times.append(elapsed)
        if i == 0:
            expected = result
    baseline = BenchResult("serial", serial_times)
    strategies = _strategies(files, chunk_size, workers)
    results: list[BenchResult] = []
    for label, fn in strategies.items():
        times: list[float] = []
        for i in range(runs):
            result, elapsed = _time_once(fn)
            if i == 0:
                _verify(label, expected, result)
            times.append(elapsed)
        results.append(BenchResult(label, times))
    return baseline, results


def _print_table(baseline: BenchResult, results: Sequence[BenchResult]) -> None:
    header = f"{'strategy':<28} {'best(s)':>9} {'avg(s)':>9} {'speedup(best)':>14}"
    logger.info(header)
    logger.info("-" * len(header))
    logger.info(f"{baseline.label:<28} {baseline.best:>9.4f} {baseline.avg:>9.4f} {'1.00x':>14}")
    for r in results:
        speedup = baseline.best / r.best if r.best > 0 else float("inf")
        logger.info(f"{r.label:<28} {r.best:>9.4f} {r.avg:>9.4f} {speedup:>13.2f}x")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        default=".",
        help="Directory whose files will be hashed (default: CWD).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=POOL_WORKERS,
        help=f"Pool size (default: {POOL_WORKERS}).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of repetitions per strategy (default: 3).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Read chunk size in bytes (default: {DEFAULT_CHUNK_SIZE}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of files (useful for quick smoke tests).",
    )
    return parser.parse_args()


def main() -> int:
    args: argparse.Namespace = parse_args()
    root = Path(args.path).resolve()
    if not root.is_dir():
        logger.error(f"Not a directory: {root}")
        return 1
    files = collect_files(root, args.limit)
    if not files:
        logger.error("No files found to hash.")
        return 1
    total_bytes = sum(p.stat().st_size for p in files)
    logger.info(f"Benchmarking {len(files)} files ({total_bytes / 1_048_576:.2f} MiB) under {root}")
    logger.info(f"workers={args.workers}  runs={args.runs}  chunk_size={args.chunk_size}")
    _ = hash_file
    baseline, results = benchmark(files, chunk_size=args.chunk_size, workers=args.workers, runs=args.runs)
    _print_table(baseline, results)
    best = min(results, key=lambda r: r.best) if results else None
    if best is not None:
        logger.info(f"Fastest strategy: {best.label} ({best.best:.4f}s, {baseline.best / best.best:.2f}x vs serial)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
