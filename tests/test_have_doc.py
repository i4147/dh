from dh import have_doc, get_pyfiles
from pathlib import Path


if __name__ == "__main__":
    cwd = Path.cwd()
    for path in get_pyfiles(cwd):
        if have_doc(path):
            print(path)
