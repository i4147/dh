from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any
from dh import (
    MAX_WORKERS,
    ParallelSummary,
    mpf,
)
@dataclass
class BenchmarkResult:
    function_name: str
    total_time: float
    throughput: float
    success_rate: float
    results: list[Any] = field(default_factory=list)
    summary: ParallelSummary | None = None
    def to_dict(self) -> dict:
        return {
            "function": self.function_name,
            "total_time": round(self.total_time, 4),
            "throughput": round(self.throughput, 2),
            "success_rate": round(self.success_rate, 2),
            "files_processed": len(self.results) if self.results else 0,
        }
def calculate_sha256(file_path: Path | str) -> tuple[str, str | None]:
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            return "", f"File not found: {file_path}"
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(8192), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest(), None
    except Exception as e:
        return "", f"Error: {type(e).__name__}: {e}"
def calculate_sha256_simple(file_path: Path | str) -> str:
    file_path = Path(file_path)
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(8192), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
def calculate_sha256_with_args(file_path: Path | str, buffer_size: int = 8192) -> str:
    file_path = Path(file_path)
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(buffer_size), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
def get_files_from_directory(directory: str | Path, extensions: list[str] | None = None) -> list[Path]:
    directory = Path(directory)
    if not directory.exists():
        print(f"Directory not found: {directory}")
        return []
    if not directory.is_dir():
        print(f"Not a directory: {directory}")
        return []
    files = []
    for file_path in directory.rglob("*"):
        if file_path.is_file() and (extensions is None or file_path.suffix.lower() in extensions):
            files.append(file_path)
    return sorted(files)
def benchmark_function(
    func: Callable, name: str, files: list[Path], workers: int = MAX_WORKERS, **kwargs
) -> BenchmarkResult:
    print(f"\n{'=' * 60}")
    print(f"Benchmarking: {name}")
    print(f"Files: {len(files)}, Workers: {workers}")
    start_time = time.perf_counter()
    try:
        if name in ["mpf3"]:
            summary = func(
                calculate_sha256,
                files,
                max_workers=workers,
                on_error=lambda item, err: print(f"  Error: {item}: {err}") if os.environ.get("DEBUG") else None,
                **kwargs,
            )
            results = []
            success_rate = summary.success_rate if summary.total > 0 else 0
        elif name in ["mpf_starmap"]:
            extra_args = [(8192,) for _ in files]
            results = func(calculate_sha256_with_args, files, extra_args=extra_args, workers=workers)
            success_rate = sum(1 for r in results if r is not None) / len(results) * 100 if results else 0
        elif name in ["mpf_joblib"]:
            results = func(calculate_sha256_simple, files, n_jobs=workers)
            success_rate = sum(1 for r in results if r is not None) / len(results) * 100 if results else 0
        else:
            results = func(calculate_sha256_simple, files, workers=workers)
            success_rate = sum(1 for r in results if r is not None) / len(results) * 100 if results else 0
        end_time = time.perf_counter()
        total_time = end_time - start_time
        throughput = len(files) / total_time if total_time > 0 else 0
        result = BenchmarkResult(
            function_name=name,
            total_time=total_time,
            throughput=throughput,
            success_rate=success_rate,
            results=results if isinstance(results, list) else [],
            summary=summary if "summary" in locals() else None,
        )
        print(f"  Time: {total_time:.3f}s")
        print(f"  Throughput: {throughput:.2f} files/s")
        print(f"  Success rate: {success_rate:.1f}%")
        return result
    except Exception as e:
        end_time = time.perf_counter()
        total_time = end_time - start_time
        print(f"  FAILED: {type(e).__name__}: {e}")
        return BenchmarkResult(
            function_name=name, total_time=total_time, throughput=0, success_rate=0, results=[], summary=None
        )
def run_benchmarks(directory: str | Path, workers: int = MAX_WORKERS, repeat: int = 3):
    print(f"Starting benchmarks...")
    print(f"Directory: {directory}")
    print(f"Workers: {workers}")
    print(f"Repeat: {repeat} times")
    files = get_files_from_directory(directory)
    if not files:
        print("No files found to process!")
        return
    print(f"Found {len(files)} files")
    total_size = sum(f.stat().st_size for f in files)
    avg_size = total_size / len(files) if files else 0
    print(f"Total size: {total_size / (1024 * 1024):.2f} MB")
    print(f"Average file size: {avg_size / 1024:.2f} KB")
    benchmark_functions = [
        ("mpf_async", mpf_async, {}),
        ("mpf_map", mpf_map, {}),
        ("mpf_imap", mpf_imap, {}),
        ("mpf_imapu", mpf_imapu, {}),
        ("mpf_starmap", mpf_starmap, {}),
        ("mpf_ppe", mpf_ppe, {}),
        ("mpf_ppe_as_completed", lambda f, files, **kw: mpf_ppe(f, files, use_as_completed=True, **kw), {}),
        ("mpf_tpe", mpf_tpe, {}),
        ("mpf3", mpf3, {"max_pending_factor": 4}),
        ("mpf", mpf, {}),
        ("mpf2", mpf2, {}),
    ]
    all_results = []
    for func_name, func, kwargs in benchmark_functions:
        if repeat > 1:
            times = []
            for i in range(repeat):
                print(f"\n--- Run {i + 1}/{repeat} for {func_name} ---")
                result = benchmark_function(func, func_name, files, workers, **kwargs)
                times.append(result.total_time)
                if i == repeat - 1:
                    final_result = result
                    final_result.total_time = statistics.mean(times)
                    final_result.throughput = len(files) / final_result.total_time if final_result.total_time > 0 else 0
            all_results.append(final_result)
        else:
            result = benchmark_function(func, func_name, files, workers, **kwargs)
            all_results.append(result)
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"{'Function':<25} {'Time (s)':<10} {'Files/s':<12} {'Success %':<10}")
    print("-" * 80)
    sorted_results = sorted(all_results, key=lambda x: x.throughput, reverse=True)
    for result in sorted_results:
        print(
            f"{result.function_name:<25} {result.total_time:<10.3f} {result.throughput:<12.2f} {result.success_rate:<10.1f}"
        )
    output_file = Path(f"benchmark_results_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_file, "w") as f:
        json.dump([r.to_dict() for r in sorted_results], f, indent=2)
    print(f"\nResults saved to: {output_file}")
    return sorted_results
def run_quick_test(directory: str | Path, workers: int = 4):
    print("Running quick test...")
    files = get_files_from_directory(directory)
    if not files:
        print("No files found!")
        return
    test_files = files[: min(5, len(files))]
    print(f"Testing with {len(test_files)} files")
    tests = [
        ("mpf_async", lambda: mpf_async(calculate_sha256_simple, test_files, workers=workers)),
        ("mpf_map", lambda: mpf_map(calculate_sha256_simple, test_files, workers=workers)),
        ("mpf_imap", lambda: mpf_imap(calculate_sha256_simple, test_files, workers=workers)),
        ("mpf_imapu", lambda: mpf_imapu(calculate_sha256_simple, test_files, workers=workers)),
        ("mpf_ppe", lambda: mpf_ppe(calculate_sha256_simple, test_files, workers=workers)),
        ("mpf_tpe", lambda: mpf_tpe(calculate_sha256_simple, test_files, workers=workers)),
        ("mpf3", lambda: mpf3(calculate_sha256, test_files, max_workers=workers)),
        ("mpf", lambda: mpf(calculate_sha256_simple, test_files, workers)),
        ("mpf2", lambda: mpf2(calculate_sha256_simple, test_files, workers)),
    ]
    for name, test_func in tests:
        try:
            start = time.perf_counter()
            results = test_func()
            elapsed = time.perf_counter() - start
            success = sum(1 for r in results if r is not None) / len(results) * 100 if results else 0
            print(f"✓ {name:<20} - {elapsed:.3f}s - {success:.0f}% success")
        except Exception as e:
            print(f"✗ {name:<20} - FAILED: {type(e).__name__}: {e}")
def create_test_files(directory: str | Path, num_files: int = 100, file_size_kb: int = 100):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    print(f"Creating {num_files} test files of {file_size_kb}KB in {directory}...")
    import random
    random.seed(42)
    for i in range(num_files):
        size = int(file_size_kb * 1024 * random.uniform(0.5, 2.0))
        file_path = directory / f"test_file_{i:04d}.txt"
        with open(file_path, "wb") as f:
            chunk_size = 8192
            remaining = size
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                f.write(os.urandom(write_size))
                remaining -= write_size
    print(f"Created {num_files} files in {directory}")
    return directory
def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark_dh.py <directory> [workers] [--create-test-files]")
        print("  directory: Directory containing files to process")
        print("  workers: Number of parallel workers (default: 8)")
        print("  --create-test-files: Create test files in the directory")
        sys.exit(1)
    directory = sys.argv[1]
    workers = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else MAX_WORKERS
    if "--create-test-files" in sys.argv:
        create_test_files(directory, num_files=200, file_size_kb=50)
    print("\n" + "=" * 60)
    print("QUICK FUNCTIONALITY TEST")
    print("=" * 60)
    run_quick_test(directory, workers=min(workers, 4))
    print("\n" + "=" * 60)
    print("FULL BENCHMARKS")
    print("=" * 60)
    results = run_benchmarks(directory, workers=workers, repeat=3)
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    if results:
        fastest = max(results, key=lambda x: x.throughput)
        print(f"Fastest function: {fastest.function_name}")
        print(f"  - Throughput: {fastest.throughput:.2f} files/s")
        print(f"  - Success rate: {fastest.success_rate:.1f}%")
        mpf3_result = next((r for r in results if r.function_name == "mpf3"), None)
        if mpf3_result:
            print(f"\nmpf3 performance: {mpf3_result.throughput:.2f} files/s")
            if mpf3_result.throughput < fastest.throughput * 0.8:
                print("  - mpf3 is significantly slower than the fastest function")
                print("  - Consider using a simpler function if you don't need advanced features")
            else:
                print("  - mpf3 performance is competitive")
        print("\nTip: For I/O-bound tasks (like file hashing), ThreadPoolExecutor might be faster.")
        print("For CPU-bound tasks, ProcessPoolExecutor is usually better.")
        print("The optimal choice depends on your specific workload.")
if __name__ == "__main__":
    main()
