from pathlib import Path

from dh import get_pyfiles, have_doc

if __name__ == "__main__":
    cwd = Path.cwd()
    for path in get_pyfiles(cwd):
        if have_doc(path):
            print(path)
