from pathlib import Path
import sys

from dh import get_file_age, get_files


def main() -> None:
    cwd = Path("/sdcard")
    args = sys.argv[1:]
    files = [Path(arg) for arg in args] if args else get_files(cwd, recursive=True, extensions=[".py"])
    for f in files:
        print(f"{f.name} : {get_file_age(f, str_mode=True)}")


if __name__ == "__main__":
    main()
