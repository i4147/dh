from pathlib import Path
from typing import Generator, Iterator, List, Union

from fastwalk import walk_dirs, walk_files

from .const import SKIP_DIRS
from .fileutils import is_binary


PathLike = Union[str, Path]


def get_dirs(
    path: PathLike,
) -> Iterator[Path]:
    for entry in walk_dirs(path):
        dirpath = Path(entry)
        if dirpath.is_dir():
            yield dirpath


def _is_python_file(file_path: str) -> bool:
    p = Path(file_path)
    if p.suffix == ".py":
        return True
    if p.suffix == "":
        try:
            with open(file_path, "rb") as fh:
                first_line = fh.readline(128).decode("utf-8", errors="ignore").lower()
            return first_line.startswith("#!") and "python" in first_line
        except OSError:
            return False
    return False


def get_files(
    path: str | Path,
    ext: list[str] | None = None,
    nobinary: bool = False,
    pyfiles: bool = False,
    skip_dirs: set[str] | None = None,
) -> list[Path]:
    out = []
    if skip_dirs is None:
        skip_dirs = SKIP_DIRS
    overrides: list[str] | None = None
    if ext and not pyfiles:
        overrides = [f"*.{e.lstrip('.')}" for e in ext]
    for file_path in walk_files(path):
        if pyfiles and not _is_python_file(file_path):
            continue
        if nobinary and is_binary(file_path):
            continue
        out.append(file_path)
    return out


def get_filez(
    path: str | Path,
    ext: list[str] | None = None,
    nobinary: bool = False,
    pyfiles: bool = False,
    skip_dirs: set[str] | None = None,
) -> Generator[Path]:
    if skip_dirs is None:
        skip_dirs = SKIP_DIRS
    overrides: list[str] | None = None
    if ext and not pyfiles:
        overrides = [f"*.{e.lstrip('.')}" for e in ext]
    for file_path in walk_files(path):
        if pyfiles and not _is_python_file(file_path):
            continue
        if nobinary and is_binary(file_path):
            continue
        yield file_path


def get_pyfiles(path: str | Path):
    return get_files(path, pyfiles=True)


def get_nobinary(path: str | Path):
    return get_files(path, nobinary=True)
