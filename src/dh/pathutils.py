from __future__ import annotations
from pathlib import Path
from typing import Iterator, Union
from fastwalk import walk_dirs, walk_files
from .fileutils import should_skip
from .isbinary import is_binary

PathLike = Union[str, Path]


def _iter_entries(
    path: PathLike,
) -> Iterator:
    for p in walk_files(path):
        filepath = Path(p)
        if should_skip(filepath):
            continue
        yield filepath


def get_files(
    path: PathLike,
    ext: list[str] | None = None,
) -> Iterator[Path]:
    exts = None if ext is None else {e.lower() for e in ext}
    for entry in _iter_entries(path):
        if exts is not None and entry.suffix.lower() not in exts:
            continue
        yield entry


def get_pyfiles(
    path: PathLike,
) -> Iterator[Path]:
    for entry in _iter_entries(path):
        if entry.suffix.lower() == ".py":
            yield entry
        elif not entry.suffix:
            try:
                with entry.open("rb") as f:
                    head = f.readline(256)
            except OSError:
                continue
            if head.startswith(b"#!") and b"python" in head:
                yield entry


def get_nobinary(
    path: PathLike,
) -> Iterator[Path]:
    for entry in _iter_entries(path):
        if not is_binary(entry):
            yield entry


def get_dirs(
    path: PathLike,
) -> Iterator[Path]:
    for entry in walk_dirs(path):
        dirpath = Path(entry)
        if dirpath.is_dir() and not should_skip(dirpath):
            yield dirpath
