import sys
from pathlib import Path
from time import perf_counter as pff
from loguru import logger
from dh import (
    get_files,
    get_sha256,
    mpf_async,
    mpf_imap,
    mpf_imap2,
    mpf_joblib,
    mpf_map,
    mpf_starmap,
    mpf_starmap2,
)

MAX_WORKERS = 4


def measure_time(func_to_process, filez: list[Path]) -> float:
    start = pff()
    func_to_process(process_file, filez)
    end = pff()
    diff_time = end - start
    logger.info(f"{func_to_process!s}: {diff_time:.3f}")
    return diff_time


def process_file(fp) -> None:
    return get_sha256(fp)


def main() -> None:
    cwd = Path.home() / "tmp" / "0"
    files = get_files(cwd)
    funcs = [
        mpf_map,
        mpf_async,
        mpf_imap,
        mpf_imap2,
        mpf_joblib,
        mpf_starmap,
        mpf_starmap2,
    ]
    results = {}
    for i in range(1, 4):
        for func in funcs:
            res = measure_time(func, files)
            results.setdefault(func, []).append(res)
    for k, v in results.items():
        print(f"{k} : {v}")


if __name__ == "__main__":
    sys.exit(main())
