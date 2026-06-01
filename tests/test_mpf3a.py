from pathlib import Path

from dh import get_files, get_sha256, mpf3a


def procf(fp):
    return get_sha256(fp)


if __name__ == "__main__":
    cwd = Path.cwd()
    files = get_files(cwd)
    mpf3a(procf, files)
