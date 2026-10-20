from pathlib import Path

from dh import clean_blank_lines, get_filez, is_binary


if __name__ == "__main__":
    cwd = Path.cwd()
    for path in get_filez(cwd):
        if not is_binary(path):
            content = path.read_text()
            nc = clean_blank_lines(content)
            print(nc)
