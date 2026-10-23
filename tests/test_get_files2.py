from pathlib import Path
import sys
from time import perf_counter as pff
from dh import get_files, get_files2, get_filez
def process_dir(fp, func) -> float:
    t1 = pff()
    _ = func(fp)
    t2 = pff()
    return t2 - t1
def run_func(path: Path) -> None:
    import secrets
    rnd = secrets.randbelow(1024 * 1024)
    reminder = rnd % 3
    tdict = {}
    if not reminder:
        g1 = process_dir(path, get_files)
        tdict[g1] = "get_files"
        g2 = process_dir(path, get_files2)
        tdict[g2] = "get_files2"
        g3 = process_dir(path, get_filez)
        tdict[g3] = "get_filez"
        best = min(g1, g2, g3)
        print(tdict.get(best))
    else:
        g1 = process_dir(path, get_filez)
        tdict[g1] = "get_filez"
        g2 = process_dir(path, get_files2)
        tdict[g2] = "get_files2"
        g3 = process_dir(path, get_files)
        tdict[g3] = "get_files"
        best = min(g1, g2, g3)
        print(tdict.get(best))
def main() -> None:
    cwd = Path.cwd()
    for _ in range(10):
        run_func(cwd)
if __name__ == "__main__":
    sys.exit(main())
