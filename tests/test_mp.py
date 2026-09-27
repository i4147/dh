import sys
from pathlib import Path
from time import perf_counter as pff
from loguru import logger
from dh import (
    get_files,
    get_sha256,
    mpf,
    mpf2,
    mpf3,
    mpf_async,
    mpf_imap,
    mpf_imapu,
    mpf_map,
    mpf_ppe,
    mpf_ppe_ac,
    mpf_starmap,
    mpf_tpe,
)
def measure_time(func_to_process, filez: list[Path]) -> None:
    start = pff()
    func_to_process(process_file, filez)
    end = pff()
    diff_time = end - start
    logger.info(f"{func_to_process!s}: {diff_time:.3f} s")
def process_file(fp) -> None:
    return get_sha256(fp)
def main() -> None:
    cwd = Path.home() / "projects"
    files = get_files(cwd)
    funcs = [mpf, mpf2, mpf3, mpf_async, mpf_imap, mpf_map, mpf_ppe, mpf_ppe_ac, mpf_tpe, mpf_starmap]
    for i in range(1, 7):
        for func in funcs:
            measure_time(func, files)
if __name__ == "__main__":
    sys.exit(main())
