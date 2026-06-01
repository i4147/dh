#!/data/data/com.termux/files/usr/bin/env python
import sys
from pathlib import Path
from time import perf_counter as pff

from dh import get_files, get_sha256, mpf, mpf2, mpf3, mpf3a, mpf3o, mpf4, mpf5
from loguru import logger


def measure_time(func_to_process, filez):
    start = pff()
    func_to_process(process_file, filez)
    end = pff()
    diff_time = end - start
    logger.info(f"{str(func_to_process)}: {diff_time}")


def process_file(fp) -> None:
    logger.info(f"{fp.name}")
    return get_sha256(fp)


def main():
    cwd = Path.home() / "tmp" / "output" / "class"
    args = sys.argv[1:]
    files = get_files(cwd)
    funcs = [mpf, mpf2, mpf3, mpf3a, mpf4, mpf5, mpf3o]
    for func in funcs:
        measure_time(func, files)


if __name__ == "__main__":
    exit(main())
