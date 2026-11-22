import codecs
from collections import defaultdict
from collections.abc import Callable, Collection, Generator, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import functools
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from typing import Any, Literal, NamedTuple, overload

from .const import BINARY_EXT, CHUNK_SIZE, EMULATED, IMAGE_EXT, SDCARD, SKIP_DIRS, TEXT_EXT, TEXT_FILENAMES, THRESHOLD
from .utils import clean_terminal_transcript


ANSI_RE: re.Pattern[str] = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
FENCE_RE: re.Pattern[str] = re.compile(r"^\s*```.*$", re.MULTILINE)
SHELL_RE: re.Pattern[str] = re.compile(r"^\s*(?:\$|>|>>>)\s.*$", re.MULTILINE)
PREAMBLE_RE: re.Pattern[str] = re.compile(
    r"^(?:sure[,!.]?|certainly[,!.]?|here(?:'s| is)[^\n]*|of course[,!.]?)\s*\n", re.IGNORECASE
)
LIVEDOC_RE: re.Pattern[str] = re.compile(r"^\s*LiveDoc\s*:.*$", re.MULTILINE | re.IGNORECASE)
RECEIVED_RE: re.Pattern[str] = re.compile(r"^\s*Received\s*:", re.MULTILINE | re.IGNORECASE)
AGENT_LINE_RE: re.Pattern[str] = re.compile(r"^\s*(?:SuperAgent|felo|feli)\b.*$", re.MULTILINE | re.IGNORECASE)
LEADING_BLANK_RE: re.Pattern[str] = re.compile(r"^\s*\n+")
SENTENCE_RE: re.Pattern[str] = re.compile(r"(?<=[.!?])\s+")
BLANK_RUN_RE: re.Pattern[str] = re.compile(r"\n{3,}")
CODING_RE: re.Pattern[str] = re.compile(r"^#.*coding[:=]")
STARTER_RE: re.Pattern[str] = re.compile(
    r"^(?:write|generate|create|build|develop|implement|make|design)\b", re.IGNORECASE
)
REFUSAL_MARKERS: tuple[str, ...] = (
    "truncated",
    "cut off",
    "paste",
    "mid-line",
    "can't produce",
    "cannot produce",
    "complete file",
)
BOLD: str = "\x1b[1m"
GREEN: str = "\x1b[32m"
YELLOW: str = "\x1b[33m"
CYAN: str = "\x1b[36m"
RED: str = "\x1b[31m"
RESET: str = "\x1b[0m"
DIM: str = "\x1b[2m"
BLUE: str = "\x1b[34m"

_NORMALIZE_RE: re.Pattern[str] = re.compile(r"[-_.]+")
_COUNTER_RE: re.Pattern[str] = re.compile(r"(?:_\d+)+$")
_FILENAME_TABLE: dict[int, str] = dict.fromkeys(range(32), "_") | {ord(c): "_" for c in '<>:"/\\|?*'}
_NON_PRINTABLE: bytes = bytes(range(32)) + bytes(range(127, 256))
_UTF8_INC = codecs.getincrementaldecoder("utf-8")
_MULTIPART_PREFIXES: frozenset[str] = frozenset({".tar", ".min", ".bundle", ".log", ".spec", ".test", ".d", ".module"})
_ARCHIVE_COMPRESSION: frozenset[str] = frozenset({".gz", ".xz", ".bz2", ".zst", ".lz"})
_AGE_UNITS: tuple[tuple[str, int], ...] = (
    ("y", 31536000),
    ("m", 2592000),
    ("d", 86400),
    ("h", 3600),
    ("min", 60),
    ("sec", 1),
)
_GLOB_CHARS: frozenset[str] = frozenset("*?[")


def fullpath(x: str | Path) -> str:
    x = str(x)
    x = os.path.expandvars(x)
    x = os.path.expanduser(x)
    x = os.path.normpath(x)
    x = os.path.abspath(x)
    return x


def _exepath(cmd: str) -> Path | None:
    for p in os.environ["PATH"].split(os.pathsep):
        fullp = Path(p) / cmd
        if os.access(fullp, os.X_OK):
            return fullp
    return None


# ---------------------------------------------------------------------------
# Path helpers (formerly _PathOps)
# ---------------------------------------------------------------------------


def suffix(name: str) -> str:
    i = name.rfind(".")
    return name[i:] if 0 < i < len(name) - 1 else ""


def split_name(name: str) -> tuple[str, str]:
    i = name.find(".", 1)
    return (name, "") if i < 0 else (name[:i], name[i:])


def require_dir(path: Path) -> None:
    if not path.exists():
        msg = f"Path does not exist: {path}"
        raise FileNotFoundError(msg)
    if not path.is_dir():
        msg = f"Path is not a directory: {path}"
        raise NotADirectoryError(msg)


def gext(path: str | Path) -> str:
    """Return the filename extension, preserving recognized compound suffixes."""
    try:
        suffs = Path(path).suffixes
    except (OSError, ValueError):
        return ""
    if not suffs:
        return ""
    if len(suffs) > 1:
        if suffs[0] in _MULTIPART_PREFIXES:
            return "".join(suffs)
        if suffs[-1] in _ARCHIVE_COMPRESSION and suffs[-2] == ".tar":
            return f".tar{suffs[-1]}"
        return suffs[-1]
    return suffs[0]


def normalize_name(name: str) -> str:
    return _NORMALIZE_RE.sub("-", name).lower()


def normalize_filename(path: str | Path) -> str:
    """Replace control characters and filesystem-unsafe filename characters."""
    return str(path).translate(_FILENAME_TABLE)


def normalize_path(path: str | Path) -> Path:
    """Resolve a path and translate the configured emulated-storage prefix."""
    try:
        s = str(path)
        if EMULATED in s:
            return Path(s.replace(EMULATED, SDCARD))
        return Path(path).resolve()
    except (OSError, ValueError):
        return Path(path)


def is_within(child_path: str | Path, parent_path: str | Path) -> bool:
    """Check whether the resolved child path is inside the parent path."""
    try:
        return Path(child_path).resolve().is_relative_to(Path(parent_path).resolve())
    except (OSError, ValueError):
        return False


def clean_fname(path: Path) -> Path:
    stem, suffix_ = split_name(path.name)
    cleaned = _COUNTER_RE.sub("", stem) or stem
    return path.with_name(cleaned + suffix_)


def unique_path(path: Path | str) -> Path:
    """Return an unused path by appending a numeric suffix when necessary."""
    path = clean_fname(Path(path))
    try:
        if not path.exists():
            return path
    except OSError:
        return path
    stem, suffix_ = split_name(path.name)
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix_}"
        try:
            if not candidate.exists():
                return candidate
        except OSError:
            return candidate
        counter += 1


def get_random_filename(length: int = 10) -> str:
    """Generate a random lowercase filename stem of the requested length."""
    from secrets import choice
    from string import ascii_lowercase

    return "".join(choice(ascii_lowercase) for _ in range(length))


def should_skip(path: str | Path) -> bool:
    """Check a path against the configured directory exclusions."""
    path = Path(path)
    try:
        return path.is_symlink() or not SKIP_DIRS.isdisjoint(path.parts)
    except OSError:
        return False


def get_mime_type(path: str | Path) -> str | None:
    """Guess the MIME type from a filename, or return None."""
    from mimetypes import guess_type

    try:
        return guess_type(str(path))[0]
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# File walking (formerly _FileWalker)
# ---------------------------------------------------------------------------


def iter_entries(
    root: Path,
    *,
    skip_dirs: Collection[str] = SKIP_DIRS,
    hidden: bool = False,
    recursive: bool = True,
) -> Iterator[tuple[Path, bool]]:
    """Yield (path, is_directory) with one scandir handle open at a time.

    DirEntry caches file-type metadata. An explicit stack avoids recursion
    limits; exclusions prune subtrees before opening them. Errors propagate
    to callers, which may retain their legacy best-effort error policies.
    """
    mode = root.lstat().st_mode
    if stat.S_ISLNK(mode):
        return
    is_dir = stat.S_ISDIR(mode)
    if not is_dir and not stat.S_ISREG(mode):
        return
    yield root, is_dir
    if not is_dir:
        return
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                if (not hidden and entry.name.startswith(".")) or entry.is_symlink():
                    continue
                is_dir = entry.is_dir(follow_symlinks=False)
                if is_dir:
                    if entry.name in skip_dirs:
                        continue
                elif not entry.is_file(follow_symlinks=False):
                    continue
                candidate = Path(entry.path)
                yield candidate, is_dir
                if is_dir and recursive:
                    pending.append(candidate)


def iter_files(
    root: Path,
    exts: set[str] | frozenset[str] | None = None,
    ends: tuple[str, ...] | None = None,
    hidden: bool = True,
    lower: bool = False,
    prune: bool = True,
) -> Iterator[Path]:
    """Filter the shared scandir engine using legacy extension semantics."""
    try:
        for candidate, is_dir in iter_entries(root, skip_dirs=SKIP_DIRS if prune else (), hidden=hidden):
            if is_dir:
                continue
            if exts is not None:
                s = suffix(candidate.name)
                if (s.lower() if lower else s) not in exts:
                    continue
            elif ends is not None and not candidate.name.endswith(ends):
                continue
            yield candidate
    except OSError:
        return


def walk_paths(inputs: str | Path | list[str | Path], ext: list[str] | None = None) -> Iterator[Path]:
    """Expand input paths and glob expressions into matching files."""
    if isinstance(inputs, (str, Path)):
        inputs = [inputs]
    exts = set(ext) if ext is not None else None
    for inp in inputs:
        path = Path(inp)
        try:
            if path.is_file():
                if exts is None or path.suffix in exts:
                    yield path
            elif path.is_dir():
                yield from iter_files(path, exts)
            else:
                parts = path.parts
                idx = next((i for i, part in enumerate(parts) if not _GLOB_CHARS.isdisjoint(part)), -1)
                if idx < 0:
                    continue
                base = Path(*parts[:idx]) if idx else Path()
                for matched in base.glob("/".join(parts[idx:])):
                    if matched.is_file():
                        if exts is None or matched.suffix in exts:
                            yield matched
                    elif matched.is_dir():
                        yield from iter_files(matched, exts)
        except (OSError, ValueError):
            continue


def walker(
    path: str | Path,
    recursive: bool = True,
    exts: list[str] | None = None,
    skip_dirs: Collection[str] = SKIP_DIRS,
) -> Iterator[Path]:
    """Iterate matching files with optional recursion and directory exclusions."""
    root = Path(path)
    try:
        if not root.is_dir():
            return
    except OSError:
        return
    suffixes: tuple[str, ...] | None = None
    if exts is not None:
        suffixes = tuple((e if e.startswith(".") else f".{e}").lower() for e in exts)

    try:
        for candidate, is_dir in iter_entries(root, skip_dirs=skip_dirs, hidden=True, recursive=recursive):
            if not is_dir and (suffixes is None or candidate.name.lower().endswith(suffixes)):
                yield candidate
    except OSError:
        return


# ---------------------------------------------------------------------------
# File operations (formerly _FileOps)
# ---------------------------------------------------------------------------


def _finish_lines(text: str, keep_ends: bool) -> list[str]:
    lines = text.splitlines(keepends=keep_ends)
    if lines and not lines[-1].endswith(("\n", "\r\n", "\r")) and text.endswith("\n"):
        lines.append("")
    return lines


def read_lines(path: str | Path, ke: bool = True) -> list[str]:
    """Read UTF-8 lines, replacing malformed bytes; optionally retain line endings."""
    path = Path(path)
    try:
        if path.stat().st_size > THRESHOLD:
            return read_lines_mmap(path, ke)
        return _finish_lines(path.read_bytes().decode("utf-8", errors="replace"), ke)
    except OSError:
        return []


def read_lines_mmap(path: Path, keep_ends: bool = True) -> list[str]:
    """Read UTF-8 lines through a read-only memory map."""
    import mmap

    path = Path(path)
    try:
        size = path.stat().st_size
        if size == 0:
            return []
        with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            text = mm[:].decode("utf-8", errors="replace")
        return _finish_lines(text, keep_ends)
    except OSError:
        return []


def write_txt_file(path: str | Path, data: str, overwrite: bool = False) -> bool:
    """Write UTF-8 text, refusing existing paths unless overwrite is enabled."""
    if not isinstance(data, str):
        return False
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not overwrite and path.exists():
            return False
        path.write_text(data, encoding="utf-8")
        return True
    except (OSError, ValueError):
        return False


def append_text(path: str | Path, content: str, encoding: str = "utf-8") -> bool:
    """Append encoded text to a file; return whether the write succeeded."""
    path = Path(path)
    try:
        if path.is_symlink() or path.is_dir():
            return False
        if not path.exists():
            path.write_text(content, encoding=encoding)
            return True
        with path.open("a", encoding=encoding) as f:
            f.write("\n" + content)
        return True
    except (OSError, ValueError):
        return False


def safe_delete(path: Path, max_retries: int = 3) -> bool:
    """Delete a file or tree, retrying transient filesystem failures."""
    from shutil import rmtree

    path = Path(path)
    for _ in range(max(1, max_retries)):
        try:
            if path.is_dir() and not path.is_symlink():
                rmtree(path)
            else:
                path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError:
            continue
    return False


def restore_bak(path: str | Path) -> bool:
    """Restore a file from its adjacent .bak backup when present."""
    path = Path(path)
    bak = path.with_name(path.name + ".bak")
    try:
        bak.replace(path)
        return True
    except OSError:
        return False


def is_empty(path: str | Path) -> bool:
    """Check whether a path names an empty directory."""
    path = Path(path)
    try:
        if not path.is_dir():
            return False
        with os.scandir(path) as it:
            return next(it, None) is None
    except OSError:
        return False


def is_image(path: str | Path) -> bool:
    """Check whether an existing file has a recognized image extension."""
    path = Path(path)
    try:
        return path.suffix.lower() in IMAGE_EXT and path.is_file()
    except (OSError, ValueError):
        return False


def _check_binary_chunk(chunk: bytes) -> bool:
    n = len(chunk)
    if not n:
        return False
    nulls = chunk.count(0)
    if nulls / n > (0.1 if n < 100 else 0.05):
        return True
    if not nulls:
        try:
            _UTF8_INC().decode(chunk)
            return False
        except UnicodeDecodeError:
            pass
    return len(chunk.translate(None, _NON_PRINTABLE)) / n < 0.7


def is_text_file(path: str | Path) -> bool:
    """Classify a file as text using extension hints and sampled content."""
    path = Path(path)
    try:
        st = path.stat()
    except FileNotFoundError:
        msg = f"File not found: {path}"
        raise FileNotFoundError(msg) from None
    except OSError as e:
        msg = f"Error checking file {path}: {e}"
        raise RuntimeError(msg) from e
    if not stat.S_ISREG(st.st_mode):
        msg = f"Path is not a file: {path}"
        raise ValueError(msg)
    suffix_ = path.suffix.lower()
    if suffix_ in BINARY_EXT:
        return False
    if suffix_ in TEXT_EXT or path.name.lower() in TEXT_FILENAMES:
        return True
    try:
        with path.open("rb") as f:
            chunk = f.read(CHUNK_SIZE)
    except OSError as e:
        msg = f"Error checking file {path}: {e}"
        raise RuntimeError(msg) from e
    return not _check_binary_chunk(chunk)


def is_python_file(path: str | Path) -> bool:
    """Recognize nonempty Python source, shebang scripts, or parseable extensionless text."""
    path = Path(path)
    try:
        st = path.stat()
    except OSError:
        return False
    if not stat.S_ISREG(st.st_mode) or st.st_size == 0:
        return False
    suffix_ = path.suffix
    if suffix_:
        return suffix_ == ".py" and is_text_file(path)
    if not is_text_file(path):
        return False
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if data.startswith(b"#!") and b"python" in data[:100]:
        return True
    try:
        from ast import parse

        parse(data.decode("utf-8"))
        return True
    except Exception:
        return False


@overload
def get_file_age(path: str | Path, str_mode: Literal[False] = False) -> float: ...
@overload
def get_file_age(path: str | Path, str_mode: Literal[True]) -> str: ...


def get_file_age(path: str | Path, str_mode: bool = False) -> float | str:
    try:
        st = Path(path).stat()
    except OSError:
        return "0 sec" if str_mode else 0.0
    if not stat.S_ISREG(st.st_mode):
        return "0 sec" if str_mode else -1.0

    mtime = getattr(st, "st_birthtime", None) or st.st_mtime
    age = time.time() - mtime
    if not str_mode:
        return age
    remaining = int(age)
    if remaining < 0:
        return "0 sec"
    parts: list[str] = []
    for name, unit in _AGE_UNITS:
        value, remaining = divmod(remaining, unit)
        if value:
            parts.append(f"{value} {name}")
    return ", ".join(parts) if parts else "0 sec"


def gsz(path: str | Path) -> int:
    path = Path(path)
    try:
        st = path.lstat()
    except OSError:
        return 0

    if stat.S_ISREG(st.st_mode):
        return st.st_size
    if not stat.S_ISDIR(st.st_mode) or path.is_symlink():
        return 0

    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        # Never follow symlinks
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def gsz_by_ext(root_dir: str | Path = ".", ext: list[str] | None = None) -> int:
    """Return the total byte size of files matching extension filters."""
    exts = {e.lower() for e in ext} if ext is not None else None
    total = 0
    try:
        for cur, _, names in os.walk(root_dir, onerror=None, followlinks=False):
            cur_p = Path(cur)
            for n in names:
                if exts is not None and suffix(n).lower() not in exts:
                    continue
                try:
                    st = (cur_p / n).lstat()
                except OSError:
                    continue
                if stat.S_ISREG(st.st_mode):
                    total += st.st_size
    except OSError:
        pass
    return total


# ---------------------------------------------------------------------------
# Directory operations (formerly _DirOps)
# ---------------------------------------------------------------------------


def copy_file(args: tuple[Path, Path]) -> tuple[bool, Path, Exception | None]:
    from shutil import copy2

    src_file, dest_file = args
    try:
        try:
            copy2(src_file, dest_file)
        except FileNotFoundError:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            copy2(src_file, dest_file)
        return (True, dest_file, None)
    except Exception as e:
        return (False, dest_file, e)


def move_file(args: tuple[Path, Path]) -> tuple[bool, Path, Exception | None]:
    from shutil import move

    src_file, dest_file = args
    try:
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        move(str(src_file), str(dest_file))
        return (True, dest_file, None)
    except Exception as e:
        return (False, dest_file, e)


def collect_tree(src_dir: Path) -> tuple[list[Path], list[Path]]:
    dirs_out: list[Path] = []
    files_out: list[Path] = []
    try:
        if not src_dir.is_dir():
            return dirs_out, files_out
        for cur, dirs, names in os.walk(src_dir, onerror=None, followlinks=False):
            cur_p = Path(cur)
            dirs_out.extend(cur_p / d for d in dirs)
            files_out.extend(cur_p / n for n in names)
    except OSError:
        pass
    return dirs_out, files_out


def copy_batch(batch: list[tuple[Path, Path]]) -> tuple[bool, Path, Exception | None]:
    last: tuple[bool, Path, Exception | None] = (True, Path(), None)
    for task in batch:
        last = copy_file(task)
        if not last[0]:
            return last
    return last


def copy_tree(src: Path, dst: Path, workers: int = 8) -> bool:
    from concurrent.futures import ThreadPoolExecutor

    try:
        dst.mkdir(parents=True, exist_ok=True)
        dirs, files = collect_tree(src)
        for d in dirs:
            (dst / d.relative_to(src)).mkdir(parents=True, exist_ok=True)
        if not files:
            return True
        tasks = [(f, dst / f.relative_to(src)) for f in files]
        n = min(workers, len(tasks))
        batches = [tasks[i::n] for i in range(n)]
        with ThreadPoolExecutor(max_workers=n) as executor:
            ok = True
            for success, dest_file, error in executor.map(copy_batch, batches):
                if not success:
                    print(f"Failed to copy {dest_file}: {error}")
                    ok = False
        return ok
    except OSError as e:
        print(f"Copy failed: {e}")
        return False


def copy_dir(src: str, dest: str) -> bool:
    """Copy a directory into a destination parent; return success."""
    try:
        src_path = Path(src).resolve()
        dest_path = Path(dest).resolve()
        if not src_path.exists():
            msg = f"Source path does not exist: {src_path}"
            raise FileNotFoundError(msg)
        if not src_path.is_dir():
            msg = f"Source must be a directory: {src_path}"
            raise NotADirectoryError(msg)
        return copy_tree(src_path, dest_path / src_path.name)
    except Exception as e:
        print(f"Copy failed: {e}")
        return False


def move_dir(src: str, dest: str) -> bool:
    """Move a directory into a destination parent; return success."""
    try:
        src_path = Path(src).resolve()
        dest_path = Path(dest).resolve()
        if not src_path.exists():
            msg = f"Source path does not exist: {src_path}"
            raise FileNotFoundError(msg)
        if not src_path.is_dir():
            msg = f"Source must be a directory: {src_path}"
            raise NotADirectoryError(msg)
        if dest_path.is_relative_to(src_path):
            print(f"Warning: Destination {dest_path} is inside source {src_path}")
            return False
        dest_folder = dest_path / src_path.name
        if dest_folder.exists():
            if next(dest_folder.iterdir(), None) is not None:
                print(f"Warning: Destination {dest_folder} already exists and is not empty")
                return False
            dest_folder.rmdir()
        dest_path.mkdir(parents=True, exist_ok=True)
        try:
            src_path.rename(dest_folder)
            return True
        except OSError:
            pass
        if not copy_tree(src_path, dest_folder):
            return False
        return safe_delete(src_path)
    except Exception as e:
        print(f"Move failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Package info (formerly _PackageInfo)
# ---------------------------------------------------------------------------


def _iter_dists() -> Iterator[tuple[str, str | None]]:
    from importlib import metadata

    for dist in metadata.distributions():
        meta = dist.metadata
        name = meta["Name"]
        if name:
            yield normalize_name(name), meta["Version"]


@functools.cache
def get_installed_packages() -> dict[str, str]:
    """Return cached installed distribution names mapped to versions."""
    packages = {name: version for name, version in _iter_dists() if version}
    return dict(sorted(packages.items()))


@functools.cache
def get_installed_pkgs() -> list[str]:
    """Return cached normalized installed distribution names."""
    return sorted(name for name, _ in _iter_dists())


# ---------------------------------------------------------------------------
# Formatting helpers (formerly _Format)
# ---------------------------------------------------------------------------


def format_bytes(n: int) -> str:
    """Format an integer byte count using binary units."""
    sign = "-" if n < 0 else ""
    value = float(abs(n))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            if unit == "B":
                return f"{sign}{int(value)} B"
            return f"{sign}{value:.2f} {unit}"
        value /= 1024.0
    return f"{sign}{value:.2f} TiB"


def fsz(n: float) -> str:
    """Format a byte count as a compact human-readable size."""
    sign = "-" if n < 0 else ""
    value = int(abs(n))
    if value == 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB", "TB")
    i = min((value.bit_length() - 1) // 10, len(units) - 1)
    if i == 0:
        return f"{sign} {value} B"
    return f"{sign} {value / (1 << (10 * i)):.2f} {units[i]}"


def format_time(t: float) -> str:
    """Format a duration in seconds using human-readable units."""
    if t <= 0:
        return "0s"
    if t < 1:
        ms = t * 1000
        return f"{ms * 1000:.0f}µs" if ms < 1 else f"{ms:.2f}ms"
    if t < 60:
        return f"{t:.0f}s"
    if t < 3600:
        m, s = divmod(int(t), 60)
        return f"{m}m, {s}s" if s else f"{m}m"
    if t < 86400:
        h, rem = divmod(int(t), 3600)
        m, s = divmod(rem, 60)
        parts = [f"{h}h"]
        if m:
            parts.append(f"{m}m")
        if s:
            parts.append(f"{s}s")
        return ", ".join(parts)
    if t < 2592000:
        d, rem = divmod(int(t), 86400)
        h, rem = divmod(rem, 3600)
        m = rem // 60
        parts = [f"{d}d"]
        if h:
            parts.append(f"{h}h")
        if m:
            parts.append(f"{m}m")
        return ", ".join(parts)
    return f"{t / 2592000:.2f} months"


def remove_blank_lines(text: str) -> str:
    """Collapse consecutive blank lines while preserving other line endings."""
    out: list[str] = []
    prev_blank = False
    for line in text.splitlines(keepends=True):
        blank = not line.strip()
        if blank and prev_blank:
            continue
        out.append(line)
        prev_blank = blank
    return "".join(out)


def get_removed_lines(txt1: str, txt2: str) -> list[str]:
    """Return unique nonempty lines in the first text but not the second."""
    other = set(txt2.splitlines())
    return [line for line in dict.fromkeys(txt1.splitlines()) if line and line not in other]


def reverse_dict(input_dict: dict[Any, Any]) -> dict[Any, Any]:
    """Invert a dictionary; duplicate values are grouped into lists."""
    values = list(input_dict.values())
    if len(set(values)) == len(values):
        return {v: k for k, v in input_dict.items()}
    rev: defaultdict[Any, list[Any]] = defaultdict(list)
    for k, v in input_dict.items():
        rev[v].append(k)
    return dict(rev)


def rrs(path: str | Path, before: float, after: float) -> None:
    """Print the before-and-after size change for a processed file."""
    p = Path(path)
    saved = before - after
    if not saved:
        msg = f"{GREEN}NO CHANGE{RESET}"
    else:
        ratio = (saved / before * 100) if before else 0.0
        sign = "+" if saved > 0 else "-"
        msg = (
            f"{GREEN}{before}->{after} = {sign} {BLUE}{fsz(saved)} {RESET} {DIM}|{RESET} {CYAN}{ratio:.1f}{DIM}%{RESET}"
        )
    print(f"{BLUE}{p.name} {RESET} {DIM}|{RESET} {msg}\n")


# ---------------------------------------------------------------------------
# Report types (kept as classes / dataclasses)
# ---------------------------------------------------------------------------


@dataclass
class FileWalkerConfig:
    skip_hidden: bool = False
    skip_symlinks: bool = True
    skip_dirs: set[str] = field(default_factory=lambda: {".git", "__pycache__"})
    file_pattern: str | None = None
    exclude_pattern: str | None = "lazy"
    max_depth: int | None = 999
    follow_symlinks: bool = False


@dataclass
class ReportItem:
    path: str
    category: str
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class ReportGenerator:
    def __init__(self, title: str = "Report", width: int = 60) -> None:
        self.title: str = title
        self.width: int = width
        self.items: list[ReportItem] = []
        self.stats: defaultdict[str, int] = defaultdict(int)

    def add_item(self, item: ReportItem) -> None:
        self.items.append(item)
        self.stats[item.category] += 1

    def add_stat(self, key: str, value: int) -> None:
        self.stats[key] = value

    def _print_header(self) -> None:
        bar = "═" * self.width
        print(
            f"\n{BOLD}{CYAN}{bar}{RESET}\n"
            f"{BOLD}{CYAN}║{RESET}{self.title.center(self.width - 2)}{BOLD}{CYAN}║{RESET}\n"
            f"{BOLD}{CYAN}{bar}{RESET}"
        )

    def _print_category_summary(
        self, category: str, items: list[ReportItem], color: str, symbol: str, show_all: bool = False
    ) -> None:
        if not items:
            return
        shown = items if show_all else items[:5]
        out = [f"\n{BOLD}{color}{symbol} {category.capitalize()}: {len(items)}{RESET}"]
        for item in shown:
            out.append(f"  {color}{symbol}{RESET} {item.path}")
            if item.message:
                out.append(f"    {DIM}{item.message}{RESET}")
        if len(items) > len(shown):
            out.append(f"  {DIM}... and {len(items) - len(shown)} more{RESET}")
        print("\n".join(out))

    def print_report(self, show_all: bool = False, sort_by: str = "path") -> None:
        self._print_header()
        if sort_by == "path":
            self.items.sort(key=lambda x: x.path)
        elif sort_by == "category":
            self.items.sort(key=lambda x: x.category)
        elif sort_by == "time":
            self.items.sort(key=lambda x: x.timestamp)
        styles: dict[str, tuple[str, str]] = {
            "success": (GREEN, "✓"),
            "binary": (YELLOW, "⊘"),
            "warning": (YELLOW, "⚠"),
            "error": (RED, "✗"),
            "info": (CYAN, "ℹ"),
        }
        buckets: dict[str, list[ReportItem]] = {k: [] for k in styles}
        for item in self.items:
            bucket = buckets.get(item.category)
            if bucket is not None:
                bucket.append(item)
        for category, items in buckets.items():
            if items:
                color, symbol = styles[category]
                self._print_category_summary(category, items, color, symbol, show_all)
        self._print_summary()

    def _print_summary(self) -> None:
        line = f"{BOLD}{CYAN}{'─' * self.width}{RESET}"
        out = [f"\n{line}", f"{BOLD}Summary:{RESET}"]
        for key, value in sorted(self.stats.items()):
            if isinstance(value, int):
                out.append(f"  {key.replace('_', ' ').title():.<30} {BOLD}{value:,}{RESET}")
        out.append(f"{line}\n")
        print("\n".join(out))

    def export_to_file(self, filepath: Path, file_format: str = "text") -> None:
        filepath = Path(filepath)
        if file_format == "text":
            out = [f"{self.title}\n{'=' * self.width}"]
            for item in self.items:
                suffix = f" - {item.message}" if item.message else ""
                out.append(f"[{item.category.upper()}] {item.path}{suffix}")
            out.append("\nSummary:")
            out.extend(f"  {key}: {value}" for key, value in self.stats.items())
            filepath.write_text("\n".join(out) + "\n", encoding="utf-8")
        elif file_format == "csv":
            import csv

            with filepath.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Path", "Category", "Message", "Timestamp"])
                writer.writerows(
                    (item.path, item.category, item.message, datetime.fromtimestamp(item.timestamp).isoformat())
                    for item in self.items
                )


# ---------------------------------------------------------------------------
# Higher-level helpers that used the classes
# ---------------------------------------------------------------------------


def get_files_scandir(path: str | Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]:
    """Return sorted files using scandir traversal and optional suffix filters."""
    path = Path(path)
    require_dir(path)
    return sorted(iter_files(path, ends=tuple(ext) if ext else None, hidden=include_hidden))


def get_files_iter(path: str | Path, ext: list[str] | None = None) -> Iterator[Path]:
    """Iterate resolved file paths without pruning default skip directories."""
    path = Path(path)
    if not path.is_dir():
        msg = f"Path is not a path: {path}"
        raise NotADirectoryError(msg)
    exts = set(ext) if ext else None
    return (p.resolve() for p in iter_files(path, exts, prune=False))


def get_filez(
    path: str | Path,
    ext: list[str] | None = None,
    nobinary: bool = False,
    pyfiles: bool = False,
    skip_dirs: set[str] | None = None,
    dirs_only: bool = False,
) -> Generator[Path, None, None]:
    """Yield paths using the shared scandir walker and combined filters.

    Extensions accept leading dots and are case-insensitive. None or an empty
    list disables extension filtering. Directory mode ignores file filters.
    The root directory itself is included in directory mode.
    Symlinks and hidden children are not followed. Traversal errors propagate.
    """
    root = Path(path)
    skipped = SKIP_DIRS if skip_dirs is None else skip_dirs
    suffixes = tuple("." + suffix_.lstrip(".").lower() for suffix_ in ext or [])
    for candidate, is_dir in iter_entries(root, skip_dirs=skipped):
        if dirs_only:
            if is_dir:
                yield candidate
            continue
        if is_dir:
            continue
        if suffixes and not candidate.name.lower().endswith(suffixes):
            continue
        if pyfiles and not _is_python_script(candidate):
            continue
        if nobinary and is_binary(candidate):
            continue
        yield candidate


def _is_python_script(path: Path) -> bool:
    """Recognize .py files and extensionless Python shebang scripts."""
    if path.suffix == ".py":
        return True
    if path.suffix:
        return False
    try:
        with path.open("rb") as stream:
            first_line = stream.readline(128).lower()
        return first_line.startswith(b"#!") and b"python" in first_line
    except OSError:
        return False


def get_files(
    path: str | Path,
    ext: list[str] | None = None,
    nobinary: bool = False,
    pyfiles: bool = False,
    skip_dirs: set[str] | None = None,
    dirs_only: bool = False,
) -> list[Path]:
    """Return sorted paths; see get_filez for filtering and root semantics."""
    return sorted(get_filez(path, ext, nobinary, pyfiles, skip_dirs, dirs_only))


def get_dirs(path: str | Path) -> Iterator[Path]:
    """Iterate directories, including the root, using the shared walker."""
    return get_filez(path, dirs_only=True)


def getfiles(root_dir: str | Path, ext: list[str] | None = None) -> list[Path]:
    """Return sorted files using the legacy scandir traversal."""
    return sorted(iter_files(Path(root_dir), set(ext) if ext is not None else None))


def get_files_pathlib(path: Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]:
    """Return sorted files with case-insensitive extension filtering."""
    path = Path(path)
    require_dir(path)
    return sorted(iter_files(path, set(ext) if ext is not None else None, hidden=include_hidden, lower=True))


def get_files4(path: str | Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]:
    """Compatibility wrapper for get_files_scandir."""
    return get_files_scandir(path, include_hidden, ext)


def get_nobinary(path: str | Path) -> list[Path]:
    """Return nonbinary files using the shared traversal filters."""
    return get_files(path, nobinary=True)


def get_pyfiles_iter(root: Path) -> Generator[Path, None, None]:
    """Yield Python files while excluding Git metadata and bytecode caches."""
    root = Path(root)
    skip = {".git", "__pycache__"}
    try:
        for cur, dirs, names in os.walk(root, onerror=None, followlinks=False):
            dirs[:] = [d for d in dirs if d not in skip]
            cur_p = Path(cur)
            for n in names:
                s = suffix(n)
                if s and s != ".py":
                    continue
                p = cur_p / n
                if not p.is_symlink() and is_python_file(p):
                    yield p
    except OSError:
        return


def get_files_iter_config(
    path: Path | str,
    config: FileWalkerConfig | None = None,
    file_filter: Callable[[Path], bool] | None = None,
) -> Iterator[Path]:
    """Yield files satisfying traversal configuration and an optional predicate."""
    cfg = config or FileWalkerConfig()
    root = Path(path).resolve()
    include_pat = cfg.file_pattern
    exclude_pat = cfg.exclude_pattern

    def accept(p: Path) -> bool:
        if include_pat and not p.match(include_pat):
            return False
        if exclude_pat and p.match(exclude_pat):
            return False
        return file_filter is None or file_filter(p)

    try:
        if not root.exists():
            print(f"{YELLOW}⚠ Warning:{RESET} '{root}' does not exist, skipping.")
            return
        if root.is_file():
            if cfg.skip_hidden and root.name.startswith("."):
                return
            if accept(root):
                yield root
            return
        if not root.is_dir():
            print(f"{YELLOW}⚠ Warning:{RESET} '{root}' is not a file or directory, skipping.")
            return
    except OSError:
        return
    skip_dirs = cfg.skip_dirs
    skip_hidden = cfg.skip_hidden
    skip_links = cfg.skip_symlinks
    max_depth = cfg.max_depth
    base_len = len(root.parts)
    try:
        for cur, dirs, names in os.walk(root, onerror=None, followlinks=cfg.follow_symlinks):
            cur_p = Path(cur)
            if max_depth is not None and len(cur_p.parts) - base_len >= max_depth:
                dirs.clear()
                continue
            dirs[:] = [
                d
                for d in dirs
                if d not in skip_dirs
                and not (skip_hidden and d.startswith("."))
                and not (skip_links and cfg.follow_symlinks and (cur_p / d).is_symlink())
            ]
            for n in names:
                if skip_hidden and n.startswith("."):
                    continue
                p = cur_p / n
                if skip_links and p.is_symlink():
                    continue
                if accept(p):
                    yield p
    except OSError:
        return


def get_pyfiles(path: str | Path) -> list[Path]:
    """Return Python source files and extensionless Python shebang scripts."""
    return get_files(path, pyfiles=True)


def worker(file_path: Path, process_fn: Callable[[Path], Any]) -> tuple[Path, Any]:
    """Apply a processor to one path, converting exceptions into ERROR strings."""
    try:
        return (file_path, process_fn(file_path))
    except Exception as e:
        return (file_path, f"ERROR: {e}")


def process_files(
    file_iter: Iterator[Path], process_fn: Callable[[Path], Any], max_workers: int = 4, prefetch: int = 128
) -> Iterator[tuple[Path, Any]]:
    """Process file batches in a spawn-based process pool and yield results."""
    from multiprocessing import get_context

    ctx = get_context("spawn")
    worker_fn = functools.partial(worker, process_fn=process_fn)
    chunk = max(1, prefetch // (max_workers * 4))
    with ctx.Pool(processes=max_workers) as pool:
        batch: list[Path] = []
        for file_path in file_iter:
            batch.append(file_path)
            if len(batch) >= prefetch:
                yield from pool.imap_unordered(worker_fn, batch, chunksize=chunk)
                batch = []
        if batch:
            yield from pool.imap_unordered(worker_fn, batch, chunksize=chunk)


def main_func(
    inputs: str | Path | list[str | Path],
    process_fn: Callable[[Path], Any],
    ext: list[str] | None = None,
    max_workers: int = 8,
    prefetch: int = 128,
    verbose: bool = True,
) -> None:
    """Process input files concurrently and optionally print a progress summary."""
    count = 0
    errors = 0
    for file_path, result in process_files(walk_paths(inputs, ext), process_fn, max_workers, prefetch):
        count += 1
        failed = str(result).startswith("ERROR")
        errors += failed
        if verbose:
            print(f"{'✗' if failed else '✓'} {file_path}: {result}")
    if verbose:
        print(f"\n{count} files processed, {errors} errors")


def walk_files(path: str | Path, ext: list[str] | None = None) -> list[Path]:
    """Return legacy scandir traversal results as a list."""
    return list(iter_files(Path(path), set(ext) if ext is not None else None))


def walkfiles(path: str | Path, ext: list[str] | None = None) -> Iterator[Path]:
    """Iterate legacy scandir traversal results."""
    return iter_files(Path(path), set(ext) if ext is not None else None)


def is_git_repo(path: str | Path) -> bool:
    """Check for a .git directory in the resolved target directory."""
    try:
        target_dir = Path(path).expanduser().resolve()
        return target_dir.is_dir() and (target_dir / ".git").is_dir()
    except (PermissionError, OSError):
        return False


def is_binary(path: str | Path) -> bool:
    """Return the inverse of the text-file classifier."""
    return not is_text_file(path)


def tree_size_kib(p: Path) -> float:
    return gsz(p) // 1024


def sorted_by_size(paths: list[Path]) -> list[tuple[float, Path]]:
    sized = [(tree_size_kib(p), p) for p in paths]
    sized.sort(key=lambda t: (t[0], str(t[1])))
    return sized


# ---------------------------------------------------------------------------
# Process runner (formerly _ProcRunner)
# ---------------------------------------------------------------------------


class RunResult(NamedTuple):
    code: int
    stdout: str
    stderr: str


def runcmd(
    cmd: Sequence[str],
    show_output: bool = True,
    timeout: float | None = None,
    stdin: str | bytes | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> RunResult:
    """Run an argument vector without a shell and return (code, stdout, stderr).

    stdin=None inherits no input (DEVNULL) for backward compatibility; pass a
    str/bytes to feed the child. env is merged over os.environ. Streams are
    cleaned with clean_terminal_transcript. Codes 127/126/124 indicate
    missing executable, permission failure, and timeout. Timeout preserves
    partial output. Invalid arguments raise immediately.
    """
    if isinstance(cmd, (str, bytes)):
        msg = "cmd must be an argument sequence, not a string"
        raise TypeError(msg)
    if not cmd:
        msg = "cmd must be a non-empty sequence of strings"
        raise ValueError(msg)
    if not cmd[0]:
        msg = "cmd[0] must be a non-empty string"
        raise ValueError(msg)
    if any(not isinstance(arg, str) for arg in cmd):
        msg = "All command arguments must be strings"
        raise TypeError(msg)
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        msg = "timeout must be a positive number or None"
        raise ValueError(msg)
    if stdin is not None and not isinstance(stdin, (str, bytes)):
        msg = "stdin must be str, bytes, or None"
        raise TypeError(msg)
    if env is not None:
        if not isinstance(env, Mapping):
            msg = "env must be a mapping of str to str"
            raise TypeError(msg)
        for k, v in env.items():
            if not isinstance(k, str) or not isinstance(v, str):
                msg = "env keys and values must be strings"
                raise TypeError(msg)

    command: list[str] = list(cmd)

    def decode_output(data: bytes | str | None) -> str:
        if data is None:
            return ""
        if isinstance(data, str):
            return clean_terminal_transcript(data) if data else ""
        return clean_terminal_transcript(data.decode("utf-8", errors="replace")) if data else ""

    def emit(stdout: str, stderr: str) -> None:
        if not show_output:
            return
        if stdout:
            sys.stdout.write(stdout)
            sys.stdout.flush()
        if stderr:
            sys.stderr.write(stderr)
            sys.stderr.flush()

    def fail(code: int, message: str) -> RunResult:
        message = clean_terminal_transcript(message)
        emit("", message)
        return RunResult(code, "", message)

    run_kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": timeout,
        "check": False,
        "text": False,
        "cwd": cwd,
    }
    if env is not None:
        run_kwargs["env"] = {**os.environ, **env}
    if stdin is None:
        run_kwargs["stdin"] = subprocess.DEVNULL
    else:
        run_kwargs["input"] = stdin.encode("utf-8") if isinstance(stdin, str) else stdin

    try:
        result = subprocess.run(command, **run_kwargs)
    except FileNotFoundError:
        return fail(127, f"Command not found: {command[0]!r}")
    except PermissionError:
        return fail(126, f"Permission denied: {command[0]!r}")
    except subprocess.TimeoutExpired as exc:
        stdout = decode_output(exc.stdout)
        stderr = decode_output(exc.stderr)
        message = f"Command timed out after {timeout}s: {' '.join(command)}"
        stderr = clean_terminal_transcript(f"{stderr.rstrip()}\n{message}".lstrip())
        emit(stdout, stderr)
        return RunResult(124, stdout, stderr)
    except OSError as exc:
        return fail(1, f"OS error running {command[0]!r}: {exc}")
    except Exception as exc:
        return fail(1, f"Unexpected error running {command[0]!r}: {exc}")

    stdout = decode_output(result.stdout)
    stderr = decode_output(result.stderr)
    emit(stdout, stderr)
    return RunResult(result.returncode, stdout, stderr)
