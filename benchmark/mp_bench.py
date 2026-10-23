from __future__ import annotations
import argparse
from collections.abc import Callable
import hashlib
from pathlib import Path
import statistics
import sys
import time
from typing import Any
from dh import (
    MAX_WORKERS,
    mpf,
    mpf2,
    mpf3,
    mpf_async,
    mpf_imap,
    mpf_imapu,
    mpf_joblib,
    mpf_map,
    mpf_ppe,
    mpf_ppe_ac,
    mpf_starmap,
    mpf_tpe,
)
def hash_file(path: Path) -> tuple[str, str]:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return str(path), h.hexdigest()
def hash_file_maybe_fail(path: Path) -> tuple[str, str | None]:
    try:
        _, digest = hash_file(path)
        return (digest, None)
    except Exception as e:
        return ("", f"{type(e).__name__}: {e}")
def _run(name: str, fn: Callable[[], Any], files: list[Path]) -> dict[str, Any]:
    print(f"\n=== {name} ===")
    print(f"files={len(files)}")
    t0 = time.perf_counter()
    try:
        result = fn()
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"  FAILED after {elapsed:.3f}s: {type(e).__name__}: {e}")
        return {"name": name, "elapsed": elapsed, "ok": False, "error": str(e)}
    elapsed = time.perf_counter() - t0
    ok = result is not None
    n_results = len(result) if hasattr(result, "__len__") else "?"
    throughput = (len(files) / elapsed) if elapsed > 0 else float("inf")
    print(f"  elapsed={elapsed:.3f}s  results={n_results}  throughput={throughput:.1f} files/s")
    return {"name": name, "elapsed": elapsed, "ok": ok, "n_results": n_results}
def benchmark(folder: Path, workers: int, runs: int, pattern: str) -> None:
    files = sorted(p for p in folder.rglob(pattern) if p.is_file())
    if not files:
        print(f"No files matched {pattern!r} under {folder}", file=sys.stderr)
        sys.exit(1)
    total_bytes = sum(f.stat().st_size for f in files)
    print(f"Folder:      {folder}")
    print(f"Pattern:     {pattern}")
    print(f"Files:       {len(files)}")
    print(f"Total size:  {total_bytes / 1e6:.2f} MB")
    print(f"Workers:     {workers}")
    print(f"Runs:        {runs}")
    benchmarks: list[tuple[str, Callable[[], Any]]] = [
        ("serial", lambda: [hash_file(f) for f in files]),
        ("mpf_map", lambda: mpf_map(hash_file, files, workers=workers)),
        ("mpf_imap", lambda: mpf_imap(hash_file, files, workers=workers, ordered=True)),
        ("mpf_imapu", lambda: mpf_imapu(hash_file, files, workers=workers)),
        ("mpf_async", lambda: mpf_async(hash_file, files, workers=workers)),
        ("mpf_starmap", lambda: mpf_starmap(hash_file, files, workers=workers)),
        ("mpf_ppe", lambda: mpf_ppe(hash_file, files, workers=workers)),
        ("mpf_ppe_ac", lambda: mpf_ppe_ac(hash_file, files, workers=workers)),
        ("mpf_tpe", lambda: mpf_tpe(hash_file, files, workers=workers)),
        ("mpf", lambda: mpf(hash_file, files, workers)),
        ("mpf2", lambda: mpf2(hash_file, files, workers)),
    ]
    if _has_joblib():
        benchmarks.append(("mpf_joblib", lambda: mpf_joblib(hash_file, files, n_jobs=workers)))
    benchmarks.append(("mpf3", lambda: mpf3(hash_file_maybe_fail, files, max_workers=workers)))
    timings: dict[str, list[float]] = {name: [] for name, _ in benchmarks}
    for r in range(runs):
        print(f"\n----- run {r + 1}/{runs} -----")
        for name, fn in benchmarks:
            info = _run(name, fn, files)
            if info["ok"]:
                timings[name].append(info["elapsed"])
    print("\n" + "=" * 72)
    print(f"{'function':<15}{'best':>10}{'median':>10}{'worst':>10}{'runs':>8}")
    print("-" * 72)
    baseline = min(timings["serial"]) if timings["serial"] else None
    for name, _ in benchmarks:
        ts = timings[name]
        if not ts:
            print(f"{name:<15}{'--':>10}{'--':>10}{'--':>10}{0:>8}")
            continue
        best = min(ts)
        med = statistics.median(ts)
        worst = max(ts)
        suffix = ""
        if baseline and name != "serial":
            suffix = f"   x{baseline / best:.2f}"
        print(f"{name:<15}{best:>9.3f}s{med:>9.3f}s{worst:>9.3f}s{len(ts):>8}{suffix}")
    print("=" * 72)
def _has_joblib() -> bool:
    try:
        import joblib
        return True
    except ImportError:
        return False
def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark dh parallel helpers on file hashing.")
    parser.add_argument("folder", type=Path, help="Folder to scan for files")
    parser.add_argument("-w", "--workers", type=int, default=MAX_WORKERS, help=f"Worker count (default {MAX_WORKERS})")
    parser.add_argument("-r", "--runs", type=int, default=3, help="Runs per benchmark (default 3)")
    parser.add_argument("-p", "--pattern", default="*", help="Glob pattern for files (default '*')")
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Only run these benchmark names (space-separated)",
    )
    args = parser.parse_args()
    if not args.folder.is_dir():
        print(f"Not a directory: {args.folder}", file=sys.stderr)
        sys.exit(1)
    benchmark(args.folder, args.workers, args.runs, args.pattern)
if __name__ == "__main__":
    main()
