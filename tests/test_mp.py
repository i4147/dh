import sys
from pathlib import Path
from time import perf_counter as pff

from dh import get_files, get_sha256, mpf, mpf2, mpf3, mpf4, mpf5
from loguru import logger


def measure_time(func_to_process, filez: list[Path]) -> None:
    start = pff()
    func_to_process(process_file, filez)
    end = pff()
    diff_time = end - start
    logger.info(f"{str(func_to_process)}: {diff_time:.3f} s")


def process_file(fp) -> None:
    #    logger.info(f"{fp.name}")
    return get_sha256(fp)


def main() -> None:
    cwd = Path.home() / "tmp" / "0"
    args = sys.argv[1:]
    files = get_files(cwd)
    funcs = [mpf5, mpf4, mpf3, mpf2, mpf]
    for i in range(1, 7):
        for func in funcs:
            measure_time(func, files)


if __name__ == "__main__":
    exit(main())
