from pathlib import Path
from dh import get_filez, get_lines, is_binary

if __name__ == "__main__":
    cwd = Path.cwd()
    for path in get_filez(cwd):
        if not is_binary(path):
            content = path.read_text()
            linez = content.splitlines(keepends=True)
            lines = get_lines(path)
            if lines == linez:
                print(f"{path.name} ok")
            else:
                print(f"{path.name} error")
