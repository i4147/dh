from pathlib import Path

from dh import get_filez


if __name__ == "__main__":
    cwd = Path.cwd()
    for path in get_filez(cwd):
        print(path.name)
