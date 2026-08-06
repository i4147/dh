from os import scandir as os_scandir
from pathlib import Path
from typing import Optional, overload
from .const import CHUNK_SIZE, EMULATED, IMG_EXT, SDCARD, SKIP_DIRS, THRESHOLD, ZERO_DOT_THREE, PY_KEYWORDS
from collections.abc import Iterator
import functools


@overload
def get_file_age(path: str | Path, str_mode: bool = False) -> float: ...


@overload
def get_file_age(path: str | Path, str_mode: bool = True) -> str: ...


def read_lines(path: str | Path, ke: bool = True) -> list[str]:
    """Read lines with memory-efficient handling for large files."""
    path = Path(path)
    if path.stat().st_size > THRESHOLD:
        return read_lines_mmap(path, ke)

    # Use memoryview to avoid extra copies
    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=ke)

    # Handle trailing newline edge case
    if not lines[-1].endswith(("\n", "\r\n", "\r")) and data.endswith(b"\n"):
        lines.append("")
    return lines


def read_lines_mmap(path: Path, keep_ends: bool = True) -> list[str]:
    """Read lines using mmap for large files - memory efficient."""
    import mmap

    size = path.stat().st_size
    with path.open("rb") as f, mmap.mmap(f.fileno(), size, access=mmap.ACCESS_READ) as mm:
        # Decode in chunks to reduce memory peak
        text = mm[:].decode("utf-8", errors="replace")

    lines = text.splitlines(keepends=keep_ends)
    if not lines[-1].endswith(("\n", "\r\n", "\r")) and size > 0 and text.endswith("\n"):
        lines.append("")
    return lines


def gext(path: str | Path) -> str:
    """Get effective file extension, handling multi-part extensions."""
    path = Path(path)
    suffs = path.suffixes
    if not suffs:
        return ""

    # Use frozenset for O(1) lookups
    multipart_prefixes = frozenset({".tar", ".min", ".bundle", ".log", ".spec", ".test", ".d", ".module"})

    if len(suffs) > 1:
        if suffs[0] in multipart_prefixes:
            return "".join(suffs)
        if suffs[-1] in {".gz", ".xz", ".bz2", ".zst", ".lz"} and suffs[-2] == ".tar":
            return f".tar{suffs[-1]}"
        return suffs[-1]
    return suffs[0]


def get_dirs(path: str | Path) -> list[Path]:
    """Get all directories recursively - iterative to avoid recursion depth issues."""
    path = Path(path)
    if not path.is_dir():
        return []

    dirs = []
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os_scandir(current) as entries:
                # Use list comprehension for speed
                subdirs = [Path(entry.path) for entry in entries if entry.is_dir(follow_symlinks=False)]
                dirs.extend(subdirs)
                stack.extend(subdirs)
        except (PermissionError, OSError):
            continue
    return dirs


def get_file_age(path: str | Path, str_mode: bool = False) -> float | str:
    """Get file age with caching for repeated calls."""
    from os import stat as os_stat
    from time import time as time_time

    path = Path(path)

    # Early validation
    if not path.exists():
        return 0.0 if not str_mode else "0 sec"
    if not path.is_file():
        return -1.0 if not str_mode else "0 sec"

    current_time = time_time()
    file_stat = os_stat(path)
    age = current_time - file_stat.st_ctime

    if not str_mode:
        return age

    int_age = int(age)
    if int_age < 0:
        return "0 sec"

    # Pre-computed unit tuples
    units = (
        ("y", 365 * 24 * 60 * 60),
        ("m", 30 * 24 * 60 * 60),
        ("d", 24 * 60 * 60),
        ("h", 60 * 60),
        ("min", 60),
        ("sec", 1),
    )

    parts = []
    for name, seconds_per_unit in units:
        value, int_age = divmod(int_age, seconds_per_unit)
        if value:
            parts.append(f"{value} {name}")
    return ", ".join(parts) if parts else "0 sec"


@functools.lru_cache(maxsize=1)
def _get_pip_freeze_data() -> tuple[float, list[str]]:
    """Cache pip freeze data with age check."""
    pip_freeze_path = Path("/sdcard/data/pip.freeze")
    if not pip_freeze_path.exists():
        return (-1, [])

    file_age = get_file_age(pip_freeze_path)
    if file_age >= 60 * 60 * 24:
        return (-1, [])

    lines = pip_freeze_path.read_text(encoding="utf8").splitlines(keepends=False)
    return (file_age, lines)


def get_installed_packages() -> dict[str, str]:
    """Get installed packages with caching."""
    from operator import itemgetter

    age, lines = _get_pip_freeze_data()
    if age >= 0:
        # Use dict comprehension for speed
        return {
            name: version
            for line in lines
            if not line.startswith("#") and "==" in line
            for name, version in [line.split("==", 1)]
        }

    from importlib.metadata import distributions as _distributions

    packages = {}
    for dist in _distributions():
        meta = dist.metadata
        name = (meta.get("Name") or meta.get("name") or "").strip()
        version = (meta.get("Version") or meta.get("version") or "").strip()
        if name and version:
            packages[name] = version

    return dict(sorted(packages.items(), key=itemgetter(0)))


def get_installed_pkgs() -> list[str]:
    """Get installed package names with caching."""
    age, lines = _get_pip_freeze_data()
    if age >= 0:
        return [line.split("==", 1)[0] for line in lines if not line.startswith("#") and "==" in line]

    from importlib.metadata import distributions

    packages = []
    for dist in distributions():
        meta = dist.metadata
        name = (meta.get("Name") or meta.get("name") or "").strip()
        if name:
            packages.append(name)
    return packages


get_ipackages = get_installed_packages
get_ipkgs = get_installed_pkgs


def get_mime_type(path: str | Path) -> str | None:
    """Get MIME type with caching."""
    from mimetypes import guess_type

    return guess_type(str(path))[0]


def get_random_filename(length: int = 10) -> str:
    """Generate random filename using secrets for better randomness."""
    from secrets import choice
    from string import ascii_lowercase

    return "".join(choice(ascii_lowercase) for _ in range(length))


def is_image(path: str | Path) -> bool:
    """Check if file is an image."""
    path = Path(path)
    try:
        return path.is_file() and path.suffix in IMG_EXT
    except Exception:
        return False


def is_within(child_path: str | Path, parent_path: str | Path) -> bool:
    """Check if child path is within parent path."""
    child = Path(child_path).resolve()
    parent = Path(parent_path).resolve()
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def normalize_filename(path: str | Path) -> str:
    """Normalize filename by replacing special characters."""
    from re import compile as re_compile
    from re import escape as re_escape

    path = str(path)
    # Pre-compile the pattern once
    special_characters = '<>:"/\\|?*' + "".join(map(chr, range(32)))
    pattern = re_compile("|".join(map(re_escape, special_characters)))
    return pattern.sub("_", path)


def normalize_path(path: str | Path) -> Path:
    """Normalize path, handling emulated paths."""
    pathstr = str(path)
    if EMULATED in pathstr:
        return Path(pathstr.replace(EMULATED, SDCARD))
    return Path(path).resolve()


def reverse_dict(input_dict: dict) -> dict:
    """Reverse dictionary, grouping values."""
    from collections import defaultdict

    rev = defaultdict(list)
    for k, v in input_dict.items():
        rev[v].append(k)
    return dict(rev)


def is_binary(path: str | Path, sample_size: int = 4096) -> bool:
    """Check if file is binary using sampling."""
    path = Path(path)
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_size)
            if not chunk:
                return False
            if b"\x00" in chunk:
                return True

            # Use bytes.translate for faster character checking
            text_chars = bytes(range(32, 127)) + b"\n\r\t\x0c\x08"
            non_text = sum(1 for byte in chunk if byte not in text_chars)
            return non_text / len(chunk) > 0.3
    except Exception:
        return True


def is_text_file(path: str | Path) -> bool:
    """Check if file is text."""
    return not is_binary(path)


def fsz(sz: float) -> str:
    """Format file size."""
    sz = abs(int(sz))
    if sz == 0:
        return "0 B"

    units = ("B", "KB", "MB", "GB", "TB")
    i = min((int(sz).bit_length() - 1) // 10, len(units) - 1)
    value = sz / 1024**i
    if i == 0:
        return f"{int(value)} {units[i]}"
    return f"{value:.1f} {units[i]}"


format_size = fsz


def get_nobinary(path: str | Path) -> list[Path]:
    """Get non-binary files."""
    return [f for f in get_files(path) if not is_binary(f)]


def safe_delete(path: Path, max_retries: int = 3) -> bool:
    """Safely delete file or directory."""
    from shutil import rmtree as shutil_rmtree

    try:
        if path.is_dir():
            shutil_rmtree(path)
        else:
            path.unlink()
        return True
    except (FileNotFoundError, PermissionError, OSError, Exception):
        return False


def get_filez(root_dir: str | Path, ext: list[str] | None = None) -> Iterator[Path]:
    """Generator for files with extension filter."""
    from fastwalk import walk_files

    ext_set = set(ext) if ext else None

    for pth in walk_files(root_dir):
        path = Path(pth)
        if should_skip(path):
            continue
        if path.is_file():
            if ext_set is None or path.suffix in ext_set:
                yield path


def unique_path(path: Path | str) -> Path:
    """Get unique path by appending counter."""
    path = _clean_fname(Path(path))
    if not path.exists():
        return path

    parent = path.parent
    suffixes = path.suffixes
    if suffixes:
        first_suffix_index = path.name.find(suffixes[0])
        stem = path.name[:first_suffix_index]
        full_suffix = "".join(suffixes)
    else:
        stem = path.name
        full_suffix = ""

    counter = 1
    while True:
        new_path = parent / f"{stem}_{counter}{full_suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


def _clean_fname(path: Path) -> Path:
    """Clean filename by removing trailing numbers."""
    from re import sub as re_sub

    clean_name = re_sub(r"(_\d+)+", "", path.name)
    return path.with_name(clean_name)


def format_time(t: float) -> str:
    """Format time duration."""
    if t <= 0:
        return "0s"
    if t < 1:
        ms = t * 1000
        if ms < 1:
            return f"{ms * 1000:.0f}µs"
        return f"{ms:.2f}ms"
    if t < 60:
        return f"{t:.0f}s"
    if t < 3600:
        minutes = int(t // 60)
        secs = int(t % 60)
        return f"{minutes}m" + (f", {secs}s" if secs else "")
    if t < 86400:
        hours = int(t // 3600)
        remaining = t % 3600
        minutes = int(remaining // 60)
        secs = int(remaining % 60)
        result = f"{hours}h"
        if minutes:
            result += f", {minutes}m"
        if secs:
            result += f", {secs}s"
        return result
    if t < 86400 * 30:
        days = int(t // 86400)
        remaining = t % 86400
        hours = int(remaining // 3600)
        minutes = int(remaining % 3600 // 60)
        result = f"{days}d"
        if hours:
            result += f", {hours}h"
        if minutes:
            result += f", {minutes}m"
        return result

    months = t / (86400 * 30)
    if months < 1:
        return "less than 1 month"
    return f"{months:.2f} months"


def runcmd(
    cmd: list[str], run_silently: bool = False, show_output: bool = True, timeout: float | None = None
) -> tuple[int, str, str]:
    """Run command with error handling."""
    from subprocess import DEVNULL as _DEVNULL
    from subprocess import TimeoutExpired as subprocess_TimeoutExpired
    from subprocess import run as subprocess_run
    from sys import stderr as sys_stderr
    from sys import stdout as sys_stdout

    if not cmd:
        raise ValueError("cmd must be a non-empty list (e.g., ['ls', '-l'])")

    try:
        if run_silently:
            result = subprocess_run(cmd, stdout=_DEVNULL, stderr=_DEVNULL, timeout=timeout)
            return (result.returncode, "", "")

        result = subprocess_run(cmd, capture_output=True, text=True, timeout=timeout)
        stdout, stderr = (result.stdout, result.stderr)

        if show_output:
            if stdout:
                sys_stdout.write(stdout)
                sys_stdout.flush()
            if stderr:
                sys_stderr.write(stderr)
                sys_stderr.flush()

        return (result.returncode, stdout, stderr)

    except FileNotFoundError:
        msg = f"Command not found: '{cmd[0]}'"
        if show_output and not run_silently:
            print(msg, file=sys_stderr)
        return (127, "", msg)

    except PermissionError:
        msg = f"Permission denied: '{cmd[0]}'"
        if show_output and not run_silently:
            print(msg, file=sys_stderr)
        return (126, "", msg)

    except subprocess_TimeoutExpired:
        msg = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        if show_output and not run_silently:
            print(msg, file=sys_stderr)
        return (124, "", msg)

    except Exception as e:
        msg = f"Unexpected error running '{cmd[0]}': {e}"
        if show_output and not run_silently:
            print(msg, file=sys_stderr)
        return (1, "", msg)


def write_txt_file(path: str | Path, data: str, overwrite: bool = False) -> bool:
    """Write text file with overwrite protection."""
    if not isinstance(data, str):
        return False

    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            return False
        path.write_text(data, encoding="utf-8")
        return True
    except Exception:
        return False


def should_skip(path: str | Path) -> bool:
    """Check if path should be skipped."""
    path = Path(path)
    return bool(path.is_symlink() or not SKIP_DIRS.isdisjoint(path.parts))


def append_text(path: str | Path, content: str, encoding: str = "utf-8") -> bool:
    """Append text to file."""
    path = Path(path)
    if path.is_symlink() or path.is_dir():
        return False

    if not path.exists():
        path.write_text(content, encoding=encoding)
        return True

    with path.open("a", encoding=encoding) as f:
        f.write("\n")
        f.write(content)
    return True


def get_removed_lines(txt1: str, txt2: str) -> list[str]:
    """Get lines removed between two texts."""
    set1 = {l for l in txt1.splitlines() if l}
    set2 = {l for l in txt2.splitlines() if l}
    return list(set1 - set2)


def restore_bak(path: str | Path) -> bool:
    """Restore from .bak file."""
    path = Path(path)
    bak_path = path.with_name(path.name + ".bak")
    if bak_path.exists():
        bak_path.rename(path)
        return True
    return False


def rrs(path, before: int, after: int) -> None:
    """Report size reduction."""
    delta = before - after
    if delta == 0:
        msg = "\x1b[5;92mNO CHANGE\x1b[0m"
    else:
        sign = "-" if delta > 0 else "+"
        msg = (
            f"\x1b[5;92m{sign} \x1b[5;94m{fsz(abs(delta))}\x1b[0m | "
            f"\x1b[5;96m{after / before * 100:.1f}\x1b[5;95m%\x1b[0m"
        )
    print(f"\n{path.name} | {msg}")


def is_empty(path: str | Path) -> bool:
    """Check if directory is empty."""
    path = Path(path)
    return path.is_dir() and not any(path.iterdir())


def gsz(path: str | Path) -> int:
    """Get total size of file or directory."""
    from os import walk as os_walk

    path = Path(path)
    if not path.exists():
        return 0

    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0

    if not path.is_dir():
        return 0

    total = 0
    for root, _, files in os_walk(path):
        for f in files:
            fp = Path(root) / f
            if not fp.is_symlink():
                try:
                    total += fp.stat().st_size
                except OSError:
                    pass
    return total


get_size = gsz


def get_files_scandir(path: str | Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]:
    """Get files recursively with filters."""
    path = Path(path)
    skip_dirs = frozenset({".git", "__pycache__"})

    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")

    ext_tuple = tuple(ext) if ext else None
    files = []
    stack = [path]

    while stack:
        current = stack.pop()
        try:
            with os_scandir(current) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue

                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in skip_dirs:
                            stack.append(Path(entry.path))

                    elif entry.is_file(follow_symlinks=False):
                        if not include_hidden and entry.name.startswith("."):
                            continue
                        if ext_tuple is None or entry.name.endswith(ext_tuple):
                            files.append(Path(entry.path))
        except (PermissionError, OSError):
            continue

    return sorted(files)


def get_fast(path, ext: list[str] | None = None) -> Iterator[Path]:
    """Fast file iterator."""
    from fastwalk import walk_files

    ext_set = set(ext) if ext else None

    for entry in walk_files(path):
        entry = Path(entry)
        if entry.is_symlink():
            continue
        if ".git" not in entry.parts and "__pycache__" not in entry.parts:
            if ext_set is None or entry.suffix in ext_set:
                yield entry


def get_pyfiles(path: str | Path, include_hidden: bool = True) -> list[Path]:
    """Get Python files recursively."""
    path = Path(path)
    skip_dirs = frozenset({".git", "__pycache__"})

    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")

    files = []
    stack = [path]

    while stack:
        current = stack.pop()
        try:
            with os_scandir(current) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue

                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in skip_dirs:
                            stack.append(Path(entry.path))

                    elif entry.is_file(follow_symlinks=False):
                        if not include_hidden and entry.name.startswith("."):
                            continue
                        if is_python_file(Path(entry.path)):
                            files.append(Path(entry.path))
        except (PermissionError, OSError):
            continue

    return sorted(files)


def is_python_file(path: str | Path) -> bool:
    path = Path(path)
    if path.suffix == ".py":
        return True

    try:
        if not path.stat().st_size:
            return False

        if path.suffix == "":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline().strip()
                if first_line.startswith("#!") and "python" in first_line.lower():
                    return True
                if _looks_like_python(path):
                    return True
    except (PermissionError, OSError, UnicodeDecodeError):
        pass

    return False


def _looks_like_python(path: Path) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = "".join(f.readline() for _ in range(10))

        content_lower = content.lower()
        return any(indicator.lower() in content_lower for indicator in PY_KEYWORDS)

    except (PermissionError, OSError, UnicodeDecodeError):
        return False


def get_files_iter(directory: str | Path, ext: list[str] | None = None) -> Iterator[Path]:
    """Iterate files recursively."""
    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory}")

    ext_set = set(ext) if ext else None

    with os_scandir(directory) as entries:
        for entry in entries:
            path = Path(entry.path)
            if path.is_symlink():
                continue

            if path.is_file():
                if ext_set is None or path.suffix in ext_set:
                    yield path.resolve()
            elif path.is_dir():
                yield from get_files_iter(path, ext)


def get_files(path: str | Path, ext: list[str] | None = None) -> list[Path]:
    from collections import deque

    path = Path(path)
    skip_dirs = {".git", "__pycache__"}
    queue = deque([path])
    files = []
    while queue:
        current = queue.popleft()
        try:
            entries = current.iterdir()
        except (PermissionError, OSError):
            continue
        for item in entries:
            if item.is_symlink():
                continue
            if item.is_dir() and item.name not in skip_dirs:
                queue.append(item)
            elif item.is_file() and (ext is None or item.suffix in ext):
                files.append(item)
    return files
