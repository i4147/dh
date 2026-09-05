from typing import Literal
from _typeshed import Incomplete

from __future__ import annotations
import contextlib
import functools
import tempfile
from collections import defaultdict
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from multiprocessing import get_context
from os import scandir as os_scandir
from pathlib import Path
from typing import Any, Optional, overload
from .const import (
    BIN_EXT,
    CHUNK_SIZE,
    EMULATED,
    IMGEXT,
    PY_KEYWORDS,
    SDCARD,
    SKIP_DIRS,
    THRESHOLD,
    TXT_EXT,
    ZERO_DOT_THREE,
)
from .isbinary import is_binary


@overload
def get_file_age(path: str | Path, str_mode: bool = False) -> float: ...


@overload
def get_file_age(path: str | Path, str_mode: bool = True) -> str: ...


def read_lines(path: str | Path, ke: bool = True) -> list[str]: ...


def read_lines_mmap(path: Path, keep_ends: bool = True) -> list[str]: ...


def gext(path: str | Path) -> str: ...


def get_dirs(path: str | Path) -> list[Path]: ...


@functools.lru_cache(maxsize=1024 * 1024)
def get_installed_packages() -> dict[str, str]: ...


@functools.lru_cache(maxsize=1024 * 1024)
def get_installed_pkgs() -> list[str]: ...


def get_mime_type(path: str | Path) -> str | None: ...


def get_random_filename(length: int = 10) -> str: ...


def is_image(path: str | Path) -> bool: ...


def is_within(child_path: str | Path, parent_path: str | Path) -> bool: ...


def normalize_filename(path: str | Path) -> str: ...


def normalize_path(path: str | Path) -> Path: ...


def reverse_dict(input_dict: dict) -> dict: ...


def fsz(sz: float) -> str: ...


def safe_delete(path: Path, max_retries: int = 3) -> bool: ...


def get_filez(root_dir: str | Path, ext: list[str] | None = None) -> Iterator[Path]: ...


def unique_path(path: Path | str) -> Path: ...


def format_time(t: float) -> str: ...


def runcmd(cmd: list[str], run_silently: bool = False, show_output: bool = True, timeout: float | None = None) -> tuple[int, str, str]: ...


def write_txt_file(path: str | Path, data: str, overwrite: bool = False) -> bool: ...


def should_skip(path: str | Path) -> bool: ...


def append_text(path: str | Path, content: str, encoding: str = "utf-8") -> bool: ...


def get_removed_lines(txt1: str, txt2: str) -> list[str]: ...


def restore_bak(path: str | Path) -> bool: ...


def rrs(path: Incomplete, before: int, after: int) -> None: ...


def is_empty(path: str | Path) -> bool: ...


def get_files_scandir(path: str | Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]: ...


def get_fast(path: Incomplete, ext: list[str] | None = None) -> Iterator[Path]: ...


def get_files_iter(directory: str | Path, ext: list[str] | None = None) -> Iterator[Path]: ...


def get_files(path: str | Path, ext: list[str] | None = None) -> list[Path]: ...


def getfiles(root_dir: str | Path, ext: list[str] | None = None) -> list[Path]: ...


def get_files_pathlib(path: Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]: ...


def get_files4(path: str | Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]: ...


def get_nobinary(path: str | Path) -> list[Path]: ...


def get_pyfiles_iter(root: Path) -> Generator[Path, None, None]: ...


def gsz(path: str | Path) -> int | float: ...


def copy_dir(src: str, dest: str) -> bool: ...


def move_dir(src: str, dest: str) -> bool: ...


BOLD: Literal['[1m'] = "\x1b[1m"
GREEN: Literal['[32m'] = "\x1b[32m"
YELLOW: Literal['[33m'] = "\x1b[33m"
CYAN: Literal['[36m'] = "\x1b[36m"
RED: Literal['[31m'] = "\x1b[31m"
RESET: Literal['[0m'] = "\x1b[0m"
DIM: Literal['[2m'] = "\x1b[2m"


@dataclass
class FileWalkerConfig:
    skip_hidden: bool = False
    skip_symlinks: bool = True
    skip_dirs: set[str]
    file_pattern: str | None = None
    exclude_pattern: str | None = "lazy"
    max_depth: int | None = 999
    follow_symlinks: bool = False

    def __init__(self, skip_hidden: bool = ..., skip_symlinks: bool = ..., skip_dirs: set[str] = ..., file_pattern: str | None = ..., exclude_pattern: str | None = ..., max_depth: int | None = ..., follow_symlinks: bool = ...) -> None: ...


def get_files_iter_config(path: Path | str, config: FileWalkerConfig | None = None, file_filter: Callable[[Path], bool] | None = None) -> Iterator[tuple[Path, Path]]: ...


@dataclass
class ReportItem:
    import time

    path: str
    category: str
    message: str = ""
    details: dict
    timestamp: float

    def __init__(self, path: str, category: str, message: str = ..., details: Incomplete = ..., timestamp: float = ...) -> None: ...


class ReportGenerator:
    items: list[ReportItem]
    stats: Incomplete
    title: str
    width: int

    def __init__(self, title: str = "Report", width: int = 60) -> None: ...

    def add_item(self, item: ReportItem) -> None: ...

    def add_stat(self, key: str, value: int) -> None: ...

    def print_report(self, show_all: bool = False, sort_by: str = "path") -> None: ...

    def export_to_file(self, filepath: Path, format: str = "text") -> None: ...


def remove_blank_lines(text: str) -> str: ...


def is_python_file(path: str | Path) -> bool: ...


def get_pyfiles(path: str | Path) -> list[Path]: ...


def walk_paths(inputs: str | Path | list[str | Path], ext: list[str] | None = None) -> Iterator[Path]: ...


def worker(file_path: Path, process_fn: Callable[[Path], Any]) -> tuple[Path, Any]: ...


def process_files(file_iter: Iterator[Path], process_fn: Callable[[Path], Any], max_workers: int = 4, prefetch: int = 128) -> Iterator[tuple[Path, Any]]: ...


def main_func(inputs: str | Path | list[str | Path], process_fn: Callable[[Path], Any], ext: list[str] | None = None, max_workers: int = 8, prefetch: int = 128, verbose: bool = True) -> None: ...


def is_text_file(path: str | Path) -> bool: ...


def atomic_write(path: Path, content: str) -> None: ...


def walk_files(path: str | Path, ext: list[str] | None = None) -> list[Path]: ...


def walkfiles(path: str | Path, ext: list[str] | None = None) -> Incomplete: ...
