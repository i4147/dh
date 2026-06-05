from os import scandir as os_scandir
from functools import lru_cache
from pathlib import Path
from .const import IMG_EXT, CHUNK_SIZE, ZERO_DOT_THREE, SKIP_DIRS, THRESHOLD, SDCARD, EMULATED
from typing import Generator


def read_lines(path: str | Path, ke: bool = True):
    path = Path(path)
    if path.stat().st_size > THRESHOLD:
        return read_lines_mmap(path, ke)
    data = Path(path).read_bytes()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=ke)
    if not lines[-1].endswith(("\n", "\r\n", "\r")) and data.endswith(b"\n"):
        lines.append("")
    return lines


def read_lines_mmap(path: Path, keep_ends: bool = True) -> list[str]:
    import mmap

    size = Path(path).stat().st_size
    with Path(path).open("rb") as f, mmap.mmap(f.fileno(), size, access=mmap.ACCESS_READ) as mm:
        text = mm[:].decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=keep_ends)
    if not lines[-1].endswith(("\n", "\r\n", "\r")) and size > 0 and text.endswith("\n"):
        lines.append("")
    return lines


def gext(path: str | Path) -> str:
    path = Path(path)
    suffs = path.suffixes
    if not suffs:
        return ""
    multipart_prefixes = {".tar", ".min", ".bundle", ".log", ".spec", ".test", ".d", ".module"}
    if len(suffs) > 1:
        if suffs[0] in multipart_prefixes:
            return "".join(suffs)
        if suffs[0] == ".tar":
            return "".join(suffs)
        if suffs[-1] in {".gz", ".xz", ".bz2", ".zst", ".lz"} and suffs[-2] == ".tar":
            return f".tar{suffs[-1]}"
        return suffs[-1]
    return suffs[0]


def mkdr(path: str | Path, exist_ok: bool = True) -> bool:
    path = Path(path)
    if path.exists():
        return False
    path.mkdir(parents=True, exist_ok=exist_ok)
    return True


def dec2hex(n: int) -> str:
    return f"{n:X}"


def decode_base64(data: str) -> bytes:
    from base64 import b64decode

    cleaned = "".join(data.split())
    return b64decode(cleaned, validate=False)


def rmfile(path: str | Path) -> bool:
    path = Path(path)
    if not path.is_file() or not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True


def rmdir(path: str | Path) -> bool:
    from shutil import rmtree as shutil_rmtree

    path = Path(path)
    if not path.exists():
        return False
    shutil_rmtree(str(path), ignore_errors=True)
    return True


def file_to_base64(path: str | Path) -> str:
    from base64 import b64encode

    path = Path(path)
    contents = path.read_bytes()
    encoded_contents = b64encode(contents)
    return encoded_contents.decode("utf-8")


def find_large_files(path: str | Path, min_size_mb: float = 1.0) -> list[tuple[Path, float]]:
    from operator import itemgetter

    path = Path(path)
    files = get_files(path)
    min_bytes = min_size_mb * 1048576
    large_files = []
    for file in files:
        size = file.stat().st_size
        if size >= min_bytes:
            large_files.append((file, size / 1048576))
    return sorted(large_files, key=itemgetter(1), reverse=True)


def get_base64(original_string: str) -> str:
    from base64 import b64encode

    bytes_data = original_string.encode("utf-8")
    return b64encode(bytes_data).decode("utf-8")


def get_dirs_recursive(path: str | Path) -> list[Path]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")
    dirs = []

    def _recurse(current_path: Path) -> None:
        try:
            for item in current_path.iterdir():
                if item.is_symlink():
                    continue
                if item.is_dir():
                    dirs.append(item)
                    _recurse(item)
        except PermissionError:
            pass

    _recurse(path)
    return sorted(dirs)


def get_dirs(path: str | Path) -> list[Path]:
    path = Path(path)
    if not path.is_dir():
        return []
    dirs = []
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os_scandir(current) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        dir_path = Path(entry.path)
                        dirs.append(dir_path)
                        stack.append(dir_path)
        except (PermissionError, OSError):
            continue
    return dirs


def get_file_age(path: str | Path, str_mode: bool = False):
    from os import stat as os_stat
    from time import time as time_time

    path = Path(path)
    current_time = time_time()
    file_stat = os_stat(path)
    file_creation_time = file_stat.st_ctime
    age = current_time - file_creation_time
    int_age = int(age)
    if not str_mode:
        if not path.exists():
            return 0.0
        if not path.is_file():
            return -1.0
        return age
    if int_age < 0:
        return "0 sec"
    units = [
        ("y", 365 * 24 * 60 * 60),
        ("m", 30 * 24 * 60 * 60),
        ("d", 24 * 60 * 60),
        ("h", 60 * 60),
        ("min", 60),
        ("sec", 1),
    ]
    parts = []
    for name, seconds_per_unit in units:
        value, int_age = divmod(int_age, seconds_per_unit)
        if value:
            parts.append(f"{value} {name}")
    return ", ".join(parts) if parts else "0 sec"


def get_installed_packages() -> dict[str, str]:
    from operator import itemgetter

    packages = {}
    pip_freeze_path = Path("/sdcard/data/pip.freeze")
    file_age = get_file_age(pip_freeze_path)
    if file_age < 60 * 60 * 24:
        lines = pip_freeze_path.read_text(encoding="utf8").splitlines(keepends=False)
        for line in lines:
            if not line.startswith("#") and "==" in line:
                name, version = line.split("==", 1)
                packages[name] = version
        return packages
    from importlib.metadata import distributions as _distributions

    for dist in _distributions():
        meta = dist.metadata
        name = meta.get("Name") or meta.get("name")
        version = meta.get("Version") or meta.get("version")
        if not name or not version:
            continue
        name = name.strip()
        packages[name] = version
    return dict(sorted(packages.items(), key=itemgetter(0)))


def get_ipackages() -> dict[str, str]:
    return get_installed_packages()


def get_installed_pkgs():
    packages = []
    pip_freeze_path = Path("/sdcard/data/pip.freeze")
    file_age = get_file_age(pip_freeze_path)
    if file_age < 60 * 60 * 24:
        lines = pip_freeze_path.read_text(encoding="utf8").splitlines(keepends=False)
        for line in lines:
            if not line.startswith("#") and "==" in line:
                name, _ = line.split("==", 1)
                packages.append(name)
        return packages
    from importlib.metadata import distributions

    for dist in distributions():
        meta = dist.metadata
        name = meta.get("Name") or meta.get("name")
        if not name:
            continue
        name = name.strip()
        packages.append(name)
    return packages


def get_ipkgs() -> list[str]:
    return get_installed_pkgs()


def get_mime_type(path: str | Path) -> str | None:
    from mimetypes import guess_type

    path = str(path)
    mime_type, _ = guess_type(path)
    return mime_type


def get_random_filename(length: int = 10) -> str:
    from random import choice
    from string import ascii_lowercase

    letters: str = ascii_lowercase
    return "".join((choice(letters) for _ in range(length)))


def hex2dec(s: str) -> int:
    return int(s, 16)


def hex_to_int(value: str):
    return tuple((int(value.lstrip("#")[i : i + 2], 16) / 255.0 for i in (0, 2, 4)))


def hex_to_rgb(value: str):
    return tuple((int(value.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)))


def is_image(path: str | Path) -> bool:
    path = Path(path)
    try:
        if not path.is_file():
            return False
        return path.suffix in IMG_EXT
    except Exception:
        return False


def is_python_file(path: str | Path) -> bool:
    from ast import parse as ast_parse

    path = Path(path)
    if is_binary(path):
        return False
    if not path.stat().st_size:
        return False
    if path.is_file() and path.suffix == ".py":
        return True
    if not path.is_file() or ".git" in path.parts:
        return False
    if not path.suffix:
        content = path.read_text(encoding="utf-8")
        if not content:
            return False
        if content.startswith("#!") and "python" in content[:100]:
            return True
        try:
            _ = ast_parse(content)
            return True
        except:
            return False
    return False


def is_within(child_path: str | Path, parent_path: str | Path) -> bool:
    child = Path(child_path).resolve()
    parent = Path(parent_path).resolve()
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_cp(src, dest, no_clobber=True):
    from shutil import copy2 as shutil_copy2
    from sys import stderr as sys_stderr

    src_path = Path(src)
    if not src_path.exists():
        print(f"Error: src '{src}' does not exist", file=sys_stderr)
        return False
    dest_path = Path(dest)
    if dest_path.is_dir():
        dest_path /= src_path.name
    if no_clobber and dest_path.exists():
        dest_path = unique_path(dest_path)
    try:
        shutil_copy2(str(src_path), str(dest_path))
        print(f"copied '{src}' -> '{dest_path}'")
        return True
    except Exception as e:
        print(f"Error copying file: {e}", file=sys_stderr)
        return False


def cpf(src: str | Path, dest: str | Path) -> bool:
    return _safe_cp(src, dest)


def _safe_mv(src, dest, no_clobber=True):
    from shutil import move as shutil_move
    from sys import stderr as sys_stderr

    src_path = Path(src)
    if not src_path.exists():
        print(f"Error: src '{src}' does not exist", file=sys_stderr)
        return False
    dest_path = Path(dest)
    if dest_path.is_dir():
        dest_path /= src_path.name
    if no_clobber and dest_path.exists():
        dest_path = unique_path(dest_path)
    try:
        shutil_move(str(src_path), str(dest_path))
        print(f"Moved '{src}' -> '{dest_path}'")
        return True
    except Exception as e:
        print(f"Error moving file: {e}", file=sys_stderr)
        return False


def move_file(src: str | Path, dest: str | Path) -> bool:
    return _safe_mv(src, dest)


def normalize_filename(path: str | Path) -> str:
    from re import compile as re_compile
    from re import escape as re_escape

    path = str(path)
    special_characters = r'<>:"/\|?*' + "".join(map(chr, range(32)))
    pattern = "|".join(map(re_escape, special_characters))
    pattern = re_compile(pattern)
    return pattern.sub("_", path)


def normalize_path(path: str | Path) -> Path:
    pathstr = str(path)
    if EMULATED in pathstr:
        return Path(pathstr.replace(EMULATED, SDCARD))
    else:
        path = Path(path)
        del pathstr
        return path.resolve()


def clean_blank_lines(lobj: str | Path) -> str:
    if isinstance(lobj, Path):
        content = lobj.read_text(encoding="utf-8", errors="ignore")
        input_is_file = True
    elif isinstance(lobj, str):
        content = lobj
        input_is_file = False
    else:
        return str(lobj)
    lines = content.splitlines(keepends=True)
    cleaned_lines = []
    previous_line_was_blank = False
    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            if not previous_line_was_blank:
                cleaned_lines.append("")
                previous_line_was_blank = True
        else:
            cleaned_lines.append(line)
            previous_line_was_blank = False
    final_content = "\n" if not cleaned_lines else "".join(cleaned_lines)
    if input_is_file:
        lobj = Path(lobj)
        lobj.write_text(final_content, encoding="utf-8")
    return final_content


def reverse_dict(input_dict: dict) -> dict:
    from collections import defaultdict

    rev = defaultdict(list)
    for k, v in input_dict.items():
        rev[v].append(k)
    return dict(rev)


def is_binary(path: Path | str) -> bool:
    path = Path(path)
    try:
        with path.open("rb") as f:
            chunk = f.read(CHUNK_SIZE)
        if not chunk:
            return False
        if b"\x00" in chunk:
            return True
        text_chars = bytearray(range(32, 127)) + b"\n\r\t\x08"
        nontext = sum((1 for b in chunk if b not in text_chars))
        return nontext / len(chunk) > ZERO_DOT_THREE
    except Exception:
        return True


def is_text_file(path: str | Path) -> bool:
    return not is_binary(path)


def fsz(sz: float) -> str:
    sz = abs(int(sz))
    units = ("B", "KB", "MB", "GB", "TB")
    if sz == 0:
        return "0 B"
    i = min((int(sz).bit_length() - 1) // 10, len(units) - 1)
    value = sz / 1024**i
    if i == 0:
        return f"{int(value)} {units[i]}"
    return f"{value:.1f} {units[i]}"


def format_size(sz: float) -> str:
    return fsz(sz)


def get_files(path: str | Path, ext: tuple[str] | None = None) -> list[Path]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")
    ext = tuple(ext) if ext else None
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
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        if ext is None or entry.name.endswith(ext):
                            files.append(Path(entry.path))
        except (PermissionError, OSError):
            continue
    return sorted(files)


def get_files2(root: str | Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]:
    root_path = Path(root).resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError("Invalid path")
    extensions = tuple(ext) if ext else None
    files = []

    def _recurse(current_path: Path) -> None:
        try:
            for entry in os_scandir(current_path):
                if entry.is_symlink():
                    continue
                if entry.name in SKIP_DIRS:
                    continue
                if not include_hidden and entry.name.startswith("."):
                    continue
                if entry.is_file(follow_symlinks=False):
                    if extensions is None or entry.name.endswith(extensions):
                        files.append(Path(entry.path).resolve())
                elif entry.is_dir(follow_symlinks=False):
                    _recurse(Path(entry.path))
        except PermissionError:
            pass

    _recurse(root_path)
    del extensions, root_path
    return sorted(files)


def get_files_iter2(
    root: str | Path, include_hidden: bool = True, ext: list[str] | None = None
) -> Generator[Path, None, None]:
    from os.path import islink, join as path_join
    from os import walk

    root = str(Path(root).resolve())
    extensions = tuple(ext) if ext else None
    for dirpath, dirnames, filenames in walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and (include_hidden or not d.startswith("."))]
        for filename in filenames:
            if not include_hidden and filename.startswith("."):
                continue
            full_path = path_join(dirpath, filename)
            if islink(full_path):
                continue
            if extensions is not None and not filename.endswith(extensions):
                continue
            yield Path(full_path).resolve()


def get_size(path: str | Path) -> int:
    from os import walk as os_walk

    path = Path(path)
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    elif path.is_dir():
        ts: int = 0
        for r, _, files in os_walk(path):
            for f in files:
                fp = Path(r) / f
                if not fp.exists() or fp.is_symlink():
                    continue
                try:
                    ts += fp.stat().st_size
                except:
                    continue
        return ts
    return 0


def get_dirs_iter(path: str | Path):
    """
    Generator version using os_scandir().
    Most efficient for extremely large trees.
    """
    path = Path(path)
    if not path.is_dir():
        return
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os_scandir(current) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        dir_path = Path(entry.path)
                        yield dir_path
                        stack.append(dir_path)
        except (PermissionError, OSError):
            continue


def get_files_iter(path: str | Path, ext: list[str] | None = None):
    """
    Generator version - yields files as they're found.
    Most memory-efficient for extremely large trees.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")
    if ext:
        ext = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in ext]
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os_scandir(current) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        file_path = Path(entry.path)
                        if ext is None or file_path.suffix.lower() in ext:
                            yield file_path
        except (PermissionError, OSError):
            continue


def get_nobinary(path: str | Path) -> list[Path]:
    return [f for f in get_files(path) if not is_binary(f)]


def get_pyfiles(path: str | Path) -> list[Path]:
    path = Path(path)
    pyfiles: list[Path] = []
    if path.is_file() and path.suffix == ".py":
        return [path]
    if path.is_dir():
        allfiles = get_files(path)
        pyfiles = [p for p in allfiles if p.suffix == ".py"]
        no_ext = [p for p in allfiles if not p.suffix]
        del allfiles
        if no_ext:
            for f in no_ext:
                if f.name.startswith("."):
                    continue
                if is_python_file(f):
                    pyfiles.append(f)
    return pyfiles


def gsz(path: str | Path) -> int:
    return get_size(path)


def safe_delete(path: Path, max_retries: int = 3) -> bool:
    from shutil import rmtree as shutil_rmtree

    try:
        if path.is_dir():
            shutil_rmtree(path)
        else:
            path.unlink()
        return True
    except FileNotFoundError:
        return True
    except PermissionError:
        return False
    except OSError as e:
        return False
    except Exception as e:
        return False
    return False


def get_filez(root_dir: str | Path):
    from os import walk as os_walk

    visited_dirs: set[Path] = set()
    root_dir = Path(root_dir)
    if root_dir.is_dir():
        for dirpath, dirnames, filenames in os_walk(root_dir, topdown=True):
            base_path = Path(dirpath)
            for dirname in list(dirnames):
                full_path = base_path / dirname
                resolved_path = full_path.resolve()
                if should_skip(full_path):
                    dirnames.remove(dirname)
                else:
                    if resolved_path in visited_dirs:
                        dirnames.remove(dirname)
                visited_dirs.add(resolved_path)
            for filename in filenames:
                filepath = Path(dirpath) / filename
                if not should_skip(filepath):
                    yield filepath
    else:
        yield root_dir


def unique_path(path: Path | str) -> Path:
    path = Path(str(path).strip("_1"))
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
        new_name = f"{stem}_{counter}{full_suffix}"
        new_path = parent / new_name
        if not new_path.exists():
            return new_path
        counter += 1


def format_time(t: float) -> str:
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
    from subprocess import DEVNULL as _DEVNULL
    from subprocess import TimeoutExpired as subprocess_TimeoutExpired
    from subprocess import run as subprocess_run
    from sys import stderr as sys_stderr
    from sys import stdout as sys_stdout

    if not cmd:
        msg = "cmd must be a non-empty list (e.g., ['ls', '-l'])"
        raise ValueError(msg)
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
        if show_output and (not run_silently):
            print(msg, file=sys_stderr)
        return (127, "", msg)
    except PermissionError:
        msg = f"Permission denied: '{cmd[0]}'"
        if show_output and (not run_silently):
            print(msg, file=sys_stderr)
        return (126, "", msg)
    except subprocess_TimeoutExpired:
        msg = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        if show_output and (not run_silently):
            print(msg, file=sys_stderr)
        return (124, "", msg)
    except Exception as e:
        msg = f"Unexpected error running '{cmd[0]}': {e}"
        if show_output and (not run_silently):
            print(msg, file=sys_stderr)
        return (1, "", msg)


def ln(label):
    from shutil import get_terminal_size as _get_terminal_size

    ts = _get_terminal_size()[0]
    label_len = len(label) + 2
    chunk = (ts - label_len) // 2
    out = f"{'-' * chunk} {label} {'-' * chunk}"
    pad = ts - len(out)
    if pad > 0:
        out += "-" * pad
    return out


def oprint(text, color="cyan", **kwargs):
    colors = {
        "black": 30,
        "red": 91,
        "green": 92,
        "yellow": 93,
        "blue": 94,
        "magenta": 95,
        "cyan": 96,
        "white": 97,
        "gray": 90,
        "default": 39,
    }
    color_code = colors.get(color.lower(), 39)
    print(f"\x1b[5;{color_code}m{text}\x1b[0m", **kwargs)


def write_txt_file(path: str | Path, data: str, overwrite: bool = False) -> bool:
    if not isinstance(data, str):
        return False
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.exists()
        if exists and (not overwrite):
            return False
        path.write_text(data, encoding="utf-8")
        return True
    except Exception:
        return False


def should_skip(path: str | Path) -> bool:
    path = Path(path)
    return bool(path.is_symlink() or not SKIP_DIRS.isdisjoint(path.parts))


def norm_str(sentence: str) -> str:
    from re import compile as re_compile

    _alnum_regex = re_compile(r"(?ui)\W")
    string_out = _alnum_regex.sub(" ", sentence)
    return string_out.strip().lower()


def prepend_text(path: str | Path, prepend_text=".min."):
    path = Path(path)
    if not path.suffix:
        msg = "The text argument expects a filename with an extension."
        raise ValueError(msg)
    new_filename = f"{path.stem}{prepend_text}{path.suffix[1:]}"
    if path.parent and path.parent != Path():
        return str(path.parent / new_filename)
    return new_filename


def append_text(path: str | Path, content: str, encoding: str = "utf-8") -> bool:
    path = Path(path)
    if path.is_symlink() or path.is_dir():
        return False
    if not path.exists():
        with path.open("w", encoding=encoding) as f:
            f.write(content)
        return True
    with path.open("a", encoding=encoding) as f:
        f.write("\n")
        f.write(content)
    return True


def get_removed_lines(txt1, txt2):
    removed = []
    added = []
    a = [p.strip() for p in txt1.splitlines() if p.strip()]
    b = [p.strip() for p in txt2.splitlines() if p.strip()]
    for k in a:
        if k not in b:
            removed.append(k)
    for x in b:
        if x not in a:
            added.append(x)
    return removed, added


def restore_bak(path: str | Path) -> bool:
    path = Path(path)
    bak_path = path.with_name(path.name + ".bak")
    if bak_path.exists():
        bak_path.rename(path)
        return True
    else:
        return False


def get_files(path: str | Path, ext: tuple[str] | None = None) -> list[Path]:
    path = Path(path)
    files: list[Path] = []
    ext = tuple(ext) if ext else None
    try:
        with os_scandir(path) as it:
            for entry in it:
                if entry.is_symlink():
                    continue
                if entry.is_file(follow_symlinks=False):
                    if ext is None or entry.name.endswith(ext):
                        files.append(Path(entry.path))
                elif entry.is_dir(follow_symlinks=False):
                    files.extend(get_files(entry.path, ext))
    except OSError:
        pass
    return files


def get_dirz(path: str | Path) -> list[Path]:
    path = Path(path)
    dirs: list[Path] = []
    try:
        with os_scandir(path) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    dirs.append(Path(entry.path))
                    dirs.extend(get_dirz(Path(entry.path)))
    except OSError:
        pass  # permission denied etc.
    return dirs


def _walk_dirs(p: Path, acc: list[Path]) -> None:
    try:
        with os_scandir(p) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    child = Path(entry.path)
                    acc.append(child)
                    _walk_dirs(child, acc)
    except OSError:
        pass
