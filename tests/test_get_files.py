from pathlib import Path

from dh import get_files

for path in get_files(".", ext=[".py"]):
    print(path)
    print()
