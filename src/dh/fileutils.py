from __future__ import annotations
import codecs
import functools
import os
import re
import stat
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, overload
from .const import BIN_EXT, CHUNK_SIZE, EMULATED, IMGEXT, SDCARD, SKIP_DIRS, THRESHOLD, TXT_EXT
from .isbinary import is_binary

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Generator, Iterator, Sequence
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


class _PathOps:
    @staticmethod
    def suffix(name: str) -> str:
        i = name.rfind(".")
        return name[i:] if 0 < i < len(name) - 1 else ""

    @staticmethod
    def split_name(name: str) -> tuple[str, str]:
        i = name.find(".", 1)
        return (name, "") if i < 0 else (name[:i], name[i:])

    @staticmethod
    def require_dir(path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")

    @staticmethod
    def gext(path: str | Path) -> str:
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

    @staticmethod
    def normalize_name(name: str) -> str:
        return _NORMALIZE_RE.sub("-", name).lower()

    @staticmethod
    def normalize_filename(path: str | Path) -> str:
        return str(path).translate(_FILENAME_TABLE)

    @staticmethod
    def normalize_path(path: str | Path) -> Path:
        try:
            s = str(path)
            if EMULATED in s:
                return Path(s.replace(EMULATED, SDCARD))
            return Path(path).resolve()
        except (OSError, ValueError):
            return Path(path)

    @staticmethod
    def is_within(child_path: str | Path, parent_path: str | Path) -> bool:
        try:
            return Path(child_path).resolve().is_relative_to(Path(parent_path).resolve())
        except (OSError, ValueError):
            return False

    @staticmethod
    def clean_fname(path: Path) -> Path:
        stem, suffix = _PathOps.split_name(path.name)
        cleaned = _COUNTER_RE.sub("", stem) or stem
        return path.with_name(cleaned + suffix)

    @staticmethod
    def unique_path(path: Path | str) -> Path:
        path = _PathOps.clean_fname(Path(path))
        try:
            if not path.exists():
                return path
        except OSError:
            return path
        stem, suffix = _PathOps.split_name(path.name)
        parent = path.parent
        counter = 1
        while True:
            candidate = parent / f"{stem}_{counter}{suffix}"
            try:
                if not candidate.exists():
                    return candidate
            except OSError:
                return candidate
            counter += 1

    @staticmethod
    def get_random_filename(length: int = 10) -> str:
        from secrets import choice
        from string import ascii_lowercase

        return "".join(choice(ascii_lowercase) for _ in range(length))

    @staticmethod
    def should_skip(path: str | Path) -> bool:
        path = Path(path)
        try:
            return path.is_symlink() or not SKIP_DIRS.isdisjoint(path.parts)
        except OSError:
            return False

    @staticmethod
    def get_mime_type(path: str | Path) -> str | None:
        from mimetypes import guess_type

        try:
            return guess_type(str(path))[0]
        except (OSError, ValueError):
            return None


class _FileWalker:
    @staticmethod
    def iter_files(
        root: Path,
        exts: set[str] | frozenset[str] | None = None,
        ends: tuple[str, ...] | None = None,
        hidden: bool = True,
        lower: bool = False,
        prune: bool = True,
    ) -> Iterator[Path]:
        try:
            for cur, dirs, names in os.walk(root, onerror=None, followlinks=False):
                if prune:
                    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                cur_p = Path(cur)
                for n in names:
                    if not hidden and n.startswith("."):
                        continue
                    if exts is not None:
                        s = _PathOps.suffix(n)
                        if (s.lower() if lower else s) not in exts:
                            continue
                    elif ends is not None and not n.endswith(ends):
                        continue
                    p = cur_p / n
                    if not p.is_symlink():
                        yield p
        except OSError:
            return

    @staticmethod
    def get_dirs(path: str | Path) -> list[Path]:
        path = Path(path)
        if not path.is_dir():
            return []
        out: list[Path] = []
        try:
            for cur, dirs, _ in os.walk(path, onerror=None, followlinks=False):
                cur_p = Path(cur)
                for d in dirs:
                    p = cur_p / d
                    if not p.is_symlink():
                        out.append(p)
        except OSError:
            pass
        return out

    @staticmethod
    def walk_paths(inputs: str | Path | list[str | Path], ext: list[str] | None = None) -> Iterator[Path]:
        if isinstance(inputs, (str, Path)):
            inputs = [inputs]
        exts = set(ext) if ext is not None else None
        for inp in inputs:
            inp = Path(inp)
            try:
                if inp.is_file():
                    if exts is None or inp.suffix in exts:
                        yield inp
                elif inp.is_dir():
                    yield from _FileWalker.iter_files(inp, exts)
                else:
                    parts = inp.parts
                    idx = next((i for i, part in enumerate(parts) if not _GLOB_CHARS.isdisjoint(part)), -1)
                    if idx < 0:
                        continue
                    base = Path(*parts[:idx]) if idx else Path()
                    for match in base.glob("/".join(parts[idx:])):
                        if match.is_file():
                            if exts is None or match.suffix in exts:
                                yield match
                        elif match.is_dir():
                            yield from _FileWalker.iter_files(match, exts)
            except (OSError, ValueError):
                continue

    @staticmethod
    def walker(
        path: str | Path,
        recursive: bool = True,
        exts: list[str] | None = None,
        skip_dirs: Collection[str] = SKIP_DIRS,
    ) -> Iterator[Path]:
        root = Path(path)
        try:
            if not root.is_dir():
                return
        except OSError:
            return
        suffixes: tuple[str, ...] | None = None
        if exts is not None:
            suffixes = tuple((e if e.startswith(".") else f".{e}").lower() for e in exts)

        def _is_regular(p: Path) -> bool:
            try:
                return stat.S_ISREG(p.lstat().st_mode)
            except OSError:
                return False

        def _matches(name: str) -> bool:
            return suffixes is None or name.lower().endswith(suffixes)

        if not recursive:
            try:
                with os.scandir(root) as it:
                    for entry in it:
                        p = Path(entry.path)
                        if _matches(entry.name) and _is_regular(p):
                            yield p
            except OSError:
                return
            return
        try:
            for dirpath, dirnames, filenames in os.walk(root, onerror=None, followlinks=False):
                if skip_dirs:
                    dirnames[:] = [d for d in dirnames if d not in skip_dirs]
                cur_p = Path(dirpath)
                for name in filenames:
                    if not _matches(name):
                        continue
                    p = cur_p / name
                    if _is_regular(p):
                        yield p
        except OSError:
            return


class _FileOps:
    @staticmethod
    def _finish_lines(text: str, keep_ends: bool) -> list[str]:
        lines = text.splitlines(keepends=keep_ends)
        if lines and not lines[-1].endswith(("\n", "\r\n", "\r")) and text.endswith("\n"):
            lines.append("")
        return lines

    @staticmethod
    def read_lines(path: str | Path, ke: bool = True) -> list[str]:
        path = Path(path)
        try:
            if path.stat().st_size > THRESHOLD:
                return _FileOps.read_lines_mmap(path, ke)
            return _FileOps._finish_lines(path.read_bytes().decode("utf-8", errors="replace"), ke)
        except OSError:
            return []

    @staticmethod
    def read_lines_mmap(path: Path, keep_ends: bool = True) -> list[str]:
        import mmap

        path = Path(path)
        try:
            size = path.stat().st_size
            if size == 0:
                return []
            with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                text = mm[:].decode("utf-8", errors="replace")
            return _FileOps._finish_lines(text, keep_ends)
        except OSError:
            return []

    @staticmethod
    def write_txt_file(path: str | Path, data: str, overwrite: bool = False) -> bool:
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

    @staticmethod
    def append_text(path: str | Path, content: str, encoding: str = "utf-8") -> bool:
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

    @staticmethod
    def safe_delete(path: Path, max_retries: int = 3) -> bool:
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

    @staticmethod
    def restore_bak(path: str | Path) -> bool:
        path = Path(path)
        bak = path.with_name(path.name + ".bak")
        try:
            bak.replace(path)
            return True
        except OSError:
            return False

    @staticmethod
    def is_empty(path: str | Path) -> bool:
        path = Path(path)
        try:
            if not path.is_dir():
                return False
            with os.scandir(path) as it:
                return next(it, None) is None
        except OSError:
            return False

    @staticmethod
    def is_image(path: str | Path) -> bool:
        path = Path(path)
        try:
            return path.suffix in IMGEXT and path.is_file()
        except (OSError, ValueError):
            return False

    @staticmethod
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

    @staticmethod
    def is_text_file(path: str | Path) -> bool:
        path = Path(path)
        try:
            st = path.stat()
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}") from None
        except OSError as e:
            raise RuntimeError(f"Error checking file {path}: {e}") from e
        if not stat.S_ISREG(st.st_mode):
            raise ValueError(f"Path is not a file: {path}")
        suffix = path.suffix
        if suffix in BIN_EXT:
            return False
        if suffix in TXT_EXT:
            return True
        try:
            with path.open("rb") as f:
                chunk = f.read(CHUNK_SIZE)
        except OSError as e:
            raise RuntimeError(f"Error checking file {path}: {e}") from e
        return not _FileOps._check_binary_chunk(chunk)

    @staticmethod
    def is_python_file(path: str | Path) -> bool:
        path = Path(path)
        try:
            st = path.stat()
        except OSError:
            return False
        if not stat.S_ISREG(st.st_mode) or st.st_size == 0:
            return False
        suffix = path.suffix
        if suffix:
            return suffix == ".py" and not is_binary(path)
        if is_binary(path):
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

    @staticmethod
    def get_file_age(path: str | Path, str_mode: bool = False) -> float | str:
        try:
            st = Path(path).stat()
        except OSError:
            return "0 sec" if str_mode else 0.0
        if not stat.S_ISREG(st.st_mode):
            return "0 sec" if str_mode else -1.0
        age = time.time() - st.st_ctime
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

    @staticmethod
    def path_size(p: Path) -> int:
        try:
            st = p.lstat()
        except OSError:
            return 0
        if stat.S_ISREG(st.st_mode):
            return st.st_size
        try:
            if p.is_dir() and not p.is_symlink():
                return _FileOps.dir_size(p)
        except OSError:
            return 0
        return 0

    @staticmethod
    def dir_size(path: Path) -> int:
        total = 0
        try:
            for cur, _, names in os.walk(path, onerror=None, followlinks=False):
                cur_p = Path(cur)
                for name in names:
                    try:
                        st = (cur_p / name).lstat()
                    except OSError:
                        continue
                    if stat.S_ISREG(st.st_mode):
                        total += st.st_size
        except OSError:
            pass
        return total

    @staticmethod
    def gsz(path: str | Path | list[str | Path]) -> float:
        try:
            if isinstance(path, list):
                total = 0
                for item in path:
                    if isinstance(item, (str, Path)):
                        total += _FileOps.path_size(Path(item))
                return float(total)
            if isinstance(path, (str, Path)):
                return float(_FileOps.path_size(Path(path)))
        except (OSError, TypeError, ValueError):
            return 0.0
        return 0.0

    @staticmethod
    def gsze(root_dir: str | Path = ".", ext: list[str] | None = None) -> int:
        exts = {e.lower() for e in ext} if ext is not None else None
        total = 0
        try:
            for cur, _, names in os.walk(root_dir, onerror=None, followlinks=False):
                cur_p = Path(cur)
                for n in names:
                    if exts is not None and _PathOps.suffix(n).lower() not in exts:
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


class _DirOps:
    @staticmethod
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

    @staticmethod
    def move_file(args: tuple[Path, Path]) -> tuple[bool, Path, Exception | None]:
        from shutil import move

        src_file, dest_file = args
        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            move(str(src_file), str(dest_file))
            return (True, dest_file, None)
        except Exception as e:
            return (False, dest_file, e)

    @staticmethod
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

    @staticmethod
    def copy_batch(batch: list[tuple[Path, Path]]) -> tuple[bool, Path, Exception | None]:
        last: tuple[bool, Path, Exception | None] = (True, Path(), None)
        for task in batch:
            last = _DirOps.copy_file(task)
            if not last[0]:
                return last
        return last

    @staticmethod
    def copy_tree(src: Path, dst: Path, workers: int = 8) -> bool:
        from concurrent.futures import ThreadPoolExecutor

        try:
            dst.mkdir(parents=True, exist_ok=True)
            dirs, files = _DirOps.collect_tree(src)
            for d in dirs:
                (dst / d.relative_to(src)).mkdir(parents=True, exist_ok=True)
            if not files:
                return True
            tasks = [(f, dst / f.relative_to(src)) for f in files]
            n = min(workers, len(tasks))
            batches = [tasks[i::n] for i in range(n)]
            with ThreadPoolExecutor(max_workers=n) as executor:
                ok = True
                for success, dest_file, error in executor.map(_DirOps.copy_batch, batches):
                    if not success:
                        print(f"Failed to copy {dest_file}: {error}")
                        ok = False
            return ok
        except OSError as e:
            print(f"Copy failed: {e}")
            return False

    @staticmethod
    def copy_dir(src: str, dest: str) -> bool:
        try:
            src_path = Path(src).resolve()
            dest_path = Path(dest).resolve()
            if not src_path.exists():
                raise FileNotFoundError(f"Source path does not exist: {src_path}")
            if not src_path.is_dir():
                raise NotADirectoryError(f"Source must be a directory: {src_path}")
            return _DirOps.copy_tree(src_path, dest_path / src_path.name)
        except Exception as e:
            print(f"Copy failed: {e}")
            return False

    @staticmethod
    def move_dir(src: str, dest: str) -> bool:
        try:
            src_path = Path(src).resolve()
            dest_path = Path(dest).resolve()
            if not src_path.exists():
                raise FileNotFoundError(f"Source path does not exist: {src_path}")
            if not src_path.is_dir():
                raise NotADirectoryError(f"Source must be a directory: {src_path}")
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
            if not _DirOps.copy_tree(src_path, dest_folder):
                return False
            return _FileOps.safe_delete(src_path)
        except Exception as e:
            print(f"Move failed: {e}")
            return False


class _ProcRunner:
    @staticmethod
    def runcmd(
        cmd: Sequence[str],
        show_output: bool = True,
        timeout: float | None = None,
    ) -> tuple[int, str, str]:
        import subprocess

        if not cmd:
            raise ValueError("cmd must be a non-empty sequence of strings")
        if not cmd[0]:
            raise ValueError("cmd[0] must be a non-empty string")
        if any(not isinstance(arg, str) for arg in cmd):
            raise TypeError("All command arguments must be strings")
        command: list[str] = list(cmd)

        def decode_output(data: bytes | str | None) -> str:
            if data is None:
                return ""
            if isinstance(data, str):
                return data
            return data.decode("utf-8", errors="replace")

        def emit(stdout: str, stderr: str) -> None:
            if not show_output:
                return
            if stdout:
                sys.stdout.write(stdout)
                sys.stdout.flush()
            if stderr:
                sys.stderr.write(stderr)
                sys.stderr.flush()

        def fail(code: int, message: str) -> tuple[int, str, str]:
            if show_output:
                print(message, file=sys.stderr, flush=True)
            return code, "", message

        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
                text=False,
            )
        except FileNotFoundError:
            return fail(127, f"Command not found: {command[0]!r}")
        except PermissionError:
            return fail(126, f"Permission denied: {command[0]!r}")
        except subprocess.TimeoutExpired as exc:
            stdout = decode_output(exc.stdout)
            stderr = decode_output(exc.stderr)
            message = f"Command timed out after {timeout}s: {' '.join(command)}"
            stderr = f"{stderr.rstrip()}\n{message}".lstrip()
            emit(stdout, stderr)
            return 124, stdout, stderr
        except OSError as exc:
            return fail(1, f"OS error running {command[0]!r}: {exc}")
        except Exception as exc:
            return fail(1, f"Unexpected error running {command[0]!r}: {exc}")
        stdout = decode_output(result.stdout)
        stderr = decode_output(result.stderr)
        emit(stdout, stderr)
        return result.returncode, stdout, stderr


class _PackageInfo:
    @staticmethod
    def _iter_dists() -> Iterator[tuple[str, str | None]]:
        from importlib import metadata

        for dist in metadata.distributions():
            meta = dist.metadata
            name = meta["Name"]
            if name:
                yield _PathOps.normalize_name(name), meta["Version"]

    @staticmethod
    @functools.cache
    def get_installed_packages() -> dict[str, str]:
        packages = {name: version for name, version in _PackageInfo._iter_dists() if version}
        return dict(sorted(packages.items()))

    @staticmethod
    @functools.cache
    def get_installed_pkgs() -> list[str]:
        return sorted(name for name, _ in _PackageInfo._iter_dists())


class _Format:
    @staticmethod
    def format_bytes(n: int) -> str:
        sign = "-" if n < 0 else ""
        value = float(abs(n))
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if value < 1024.0 or unit == "TiB":
                if unit == "B":
                    return f"{sign}{int(value)} B"
                return f"{sign}{value:.2f} {unit}"
            value /= 1024.0
        return f"{sign}{value:.2f} TiB"

    @staticmethod
    def fsz(n: int | float) -> str:
        sign = "-" if n < 0 else ""
        value = int(abs(n))
        if value == 0:
            return "0 B"
        units = ("B", "KB", "MB", "GB", "TB")
        i = min((value.bit_length() - 1) // 10, len(units) - 1)
        if i == 0:
            return f"{sign} {value} B"
        return f"{sign} {value / (1 << (10 * i)):.2f} {units[i]}"

    @staticmethod
    def format_time(t: float) -> str:
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

    @staticmethod
    def remove_blank_lines(text: str) -> str:
        out: list[str] = []
        prev_blank = False
        for line in text.splitlines(keepends=True):
            blank = not line.strip()
            if blank and prev_blank:
                continue
            out.append(line)
            prev_blank = blank
        return "".join(out)

    @staticmethod
    def get_removed_lines(txt1: str, txt2: str) -> list[str]:
        other = set(txt2.splitlines())
        return [line for line in dict.fromkeys(txt1.splitlines()) if line and line not in other]

    @staticmethod
    def reverse_dict(input_dict: dict[Any, Any]) -> dict[Any, Any]:
        values = list(input_dict.values())
        if len(set(values)) == len(values):
            return {v: k for k, v in input_dict.items()}
        rev: defaultdict[Any, list[Any]] = defaultdict(list)
        for k, v in input_dict.items():
            rev[v].append(k)
        return dict(rev)

    @staticmethod
    def rrs(path: str | Path, before: int, after: int) -> None:
        p = Path(path)
        saved = before - after
        if not saved:
            msg = f"{GREEN}NO CHANGE{RESET}"
        else:
            ratio = (saved / before * 100) if before else 0.0
            sign = "+" if saved > 0 else "-"
            msg = (
                f"{GREEN}{before}->{after} = {sign} {BLUE}{_Format.fsz(saved)} {RESET} "
                f"{DIM}|{RESET} {CYAN}{ratio:.1f}{DIM}%{RESET}"
            )
        print(f"{BLUE}{p.name} {RESET} {DIM}|{RESET} {msg}\n")


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

    def export_to_file(self, filepath: Path, format: str = "text") -> None:
        filepath = Path(filepath)
        if format == "text":
            out = [f"{self.title}\n{'=' * self.width}"]
            for item in self.items:
                suffix = f" - {item.message}" if item.message else ""
                out.append(f"[{item.category.upper()}] {item.path}{suffix}")
            out.append("\nSummary:")
            out.extend(f"  {key}: {value}" for key, value in self.stats.items())
            filepath.write_text("\n".join(out) + "\n", encoding="utf-8")
        elif format == "csv":
            import csv

            with filepath.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Path", "Category", "Message", "Timestamp"])
                writer.writerows(
                    (item.path, item.category, item.message, datetime.fromtimestamp(item.timestamp).isoformat())
                    for item in self.items
                )


def read_lines(path: str | Path, ke: bool = True) -> list[str]:
    return _FileOps.read_lines(path, ke)


def read_lines_mmap(path: Path, keep_ends: bool = True) -> list[str]:
    return _FileOps.read_lines_mmap(path, keep_ends)


def gext(path: str | Path) -> str:
    return _PathOps.gext(path)


def get_dirs(path: str | Path) -> list[Path]:
    return _FileWalker.get_dirs(path)


@overload
def get_file_age(path: str | Path, str_mode: Literal[False] = False) -> float: ...
@overload
def get_file_age(path: str | Path, str_mode: Literal[True]) -> str: ...
def get_file_age(path: str | Path, str_mode: bool = False) -> float | str:
    return _FileOps.get_file_age(path, str_mode)


def get_installed_packages() -> dict[str, str]:
    return _PackageInfo.get_installed_packages()


def get_installed_pkgs() -> list[str]:
    return _PackageInfo.get_installed_pkgs()


def get_mime_type(path: str | Path) -> str | None:
    return _PathOps.get_mime_type(path)


def get_random_filename(length: int = 10) -> str:
    return _PathOps.get_random_filename(length)


def is_image(path: str | Path) -> bool:
    return _FileOps.is_image(path)


def is_within(child_path: str | Path, parent_path: str | Path) -> bool:
    return _PathOps.is_within(child_path, parent_path)


def normalize_filename(path: str | Path) -> str:
    return _PathOps.normalize_filename(path)


def normalize_path(path: str | Path) -> Path:
    return _PathOps.normalize_path(path)


def reverse_dict(input_dict: dict[Any, Any]) -> dict[Any, Any]:
    return _Format.reverse_dict(input_dict)


def format_bytes(n: int) -> str:
    return _Format.format_bytes(n)


def fsz(n: int | float) -> str:
    return _Format.fsz(n)


def safe_delete(path: Path, max_retries: int = 3) -> bool:
    return _FileOps.safe_delete(path, max_retries)


def get_filez(root_dir: str | Path, ext: list[str] | None = None) -> Iterator[Path]:
    return _FileWalker.iter_files(Path(root_dir), set(ext) if ext else None)


def unique_path(path: Path | str) -> Path:
    return _PathOps.unique_path(path)


def format_time(t: float) -> str:
    return _Format.format_time(t)


def runcmd(
    cmd: Sequence[str],
    show_output: bool = True,
    timeout: float | None = None,
) -> tuple[int, str, str]:
    return _ProcRunner.runcmd(cmd, show_output, timeout)


def write_txt_file(path: str | Path, data: str, overwrite: bool = False) -> bool:
    return _FileOps.write_txt_file(path, data, overwrite)


def should_skip(path: str | Path) -> bool:
    return _PathOps.should_skip(path)


def append_text(path: str | Path, content: str, encoding: str = "utf-8") -> bool:
    return _FileOps.append_text(path, content, encoding)


def get_removed_lines(txt1: str, txt2: str) -> list[str]:
    return _Format.get_removed_lines(txt1, txt2)


def restore_bak(path: str | Path) -> bool:
    return _FileOps.restore_bak(path)


def rrs(path: str | Path, before: int, after: int) -> None:
    _Format.rrs(path, before, after)


def is_empty(path: str | Path) -> bool:
    return _FileOps.is_empty(path)


def get_files_scandir(path: str | Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]:
    path = Path(path)
    _PathOps.require_dir(path)
    return sorted(_FileWalker.iter_files(path, ends=tuple(ext) if ext else None, hidden=include_hidden))


def get_files_iter(directory: str | Path, ext: list[str] | None = None) -> Iterator[Path]:
    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory}")
    exts = set(ext) if ext else None
    return (p.resolve() for p in _FileWalker.iter_files(directory, exts, prune=False))


def get_files(path: str | Path, ext: list[str] | None = None) -> list[Path]:
    return sorted(_FileWalker.iter_files(Path(path), set(ext) if ext is not None else None))


def getfiles(root_dir: str | Path, ext: list[str] | None = None) -> list[Path]:
    return sorted(_FileWalker.iter_files(Path(root_dir), set(ext) if ext is not None else None))


def get_files_pathlib(path: Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]:
    path = Path(path)
    _PathOps.require_dir(path)
    return sorted(
        _FileWalker.iter_files(path, set(ext) if ext is not None else None, hidden=include_hidden, lower=True)
    )


def get_files4(path: str | Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]:
    return get_files_scandir(path, include_hidden, ext)


def get_nobinary(path: str | Path) -> list[Path]:
    return [f for f in get_files(path) if not is_binary(f)]


def get_pyfiles_iter(root: Path) -> Generator[Path, None, None]:
    root = Path(root)
    skip = {".git", "__pycache__"}
    try:
        for cur, dirs, names in os.walk(root, onerror=None, followlinks=False):
            dirs[:] = [d for d in dirs if d not in skip]
            cur_p = Path(cur)
            for n in names:
                s = _PathOps.suffix(n)
                if s and s != ".py":
                    continue
                p = cur_p / n
                if not p.is_symlink() and _FileOps.is_python_file(p):
                    yield p
    except OSError:
        return


def gsz(path: str | Path | list[str | Path]) -> float:
    return _FileOps.gsz(path)


def copy_dir(src: str, dest: str) -> bool:
    return _DirOps.copy_dir(src, dest)


def move_dir(src: str, dest: str) -> bool:
    return _DirOps.move_dir(src, dest)


def get_files_iter_config(
    path: Path | str,
    config: FileWalkerConfig | None = None,
    file_filter: Callable[[Path], bool] | None = None,
) -> Iterator[Path]:
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


def remove_blank_lines(text: str) -> str:
    return _Format.remove_blank_lines(text)


def is_python_file(path: str | Path) -> bool:
    return _FileOps.is_python_file(path)


def get_pyfiles(path: str | Path) -> list[Path]:
    path = Path(path)
    try:
        if path.is_file():
            suffix = path.suffix
            if suffix == ".py":
                return [path]
            if not suffix and not path.name.startswith(".") and _FileOps.is_python_file(path):
                return [path]
            return []
        if not path.is_dir():
            return []
    except OSError:
        return []
    found: list[Path] = []
    try:
        for cur, dirs, names in os.walk(path, onerror=None, followlinks=False):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            cur_p = Path(cur)
            for n in names:
                s = _PathOps.suffix(n)
                if s == ".py":
                    p = cur_p / n
                    if not p.is_symlink():
                        found.append(p)
                elif not s and not n.startswith("."):
                    p = cur_p / n
                    if not p.is_symlink() and _FileOps.is_python_file(p):
                        found.append(p)
    except OSError:
        pass
    return sorted(found)


def walk_paths(inputs: str | Path | list[str | Path], ext: list[str] | None = None) -> Iterator[Path]:
    return _FileWalker.walk_paths(inputs, ext)


def worker(file_path: Path, process_fn: Callable[[Path], Any]) -> tuple[Path, Any]:
    try:
        return (file_path, process_fn(file_path))
    except Exception as e:
        return (file_path, f"ERROR: {e}")


def process_files(
    file_iter: Iterator[Path], process_fn: Callable[[Path], Any], max_workers: int = 4, prefetch: int = 128
) -> Iterator[tuple[Path, Any]]:
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


def is_text_file(path: str | Path) -> bool:
    return _FileOps.is_text_file(path)


def walk_files(path: str | Path, ext: list[str] | None = None) -> list[Path]:
    return list(_FileWalker.iter_files(Path(path), set(ext) if ext is not None else None))


def walkfiles(path: str | Path, ext: list[str] | None = None) -> Iterator[Path]:
    return _FileWalker.iter_files(Path(path), set(ext) if ext is not None else None)


def gsze(root_dir: str | Path = ".", ext: list[str] | None = None) -> int:
    return _FileOps.gsze(root_dir, ext)


def walker(
    path: str | Path,
    recursive: bool = True,
    exts: list[str] | None = None,
    skip_dirs: Collection[str] = SKIP_DIRS,
) -> Iterator[Path]:
    return _FileWalker.walker(path, recursive, exts, skip_dirs)
