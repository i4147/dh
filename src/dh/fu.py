from collections.abc import Generator
from os import scandir as os_scandir
from pathlib import Path

from .const import SKIP_DIRS


def mkdr(path: (str | Path), exist_ok: bool = True) -> bool:
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


def rmfile(path: (str | Path)) -> bool:
    path = Path(path)
    if not path.is_file() or not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True


def rmdir(path: (str | Path)) -> bool:
    from shutil import rmtree as shutil_rmtree

    path = Path(path)
    if not path.exists():
        return False
    shutil_rmtree(str(path), ignore_errors=True)
    return True


def file_to_base64(path: (str | Path)) -> str:
    from base64 import b64encode

    path = Path(path)
    contents = path.read_bytes()
    encoded_contents = b64encode(contents)
    return encoded_contents.decode("utf-8")


def find_large_files(path: (str | Path), min_size_mb: float = 1.0) -> list[tuple[Path, float]]:
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


def get_dirs_recursive(path: (str | Path)) -> list[Path]:
    path = Path(path)
    if not path.exists():
        msg = f"Path does not exist: {path}"
        raise FileNotFoundError(msg)
    if not path.is_dir():
        msg = f"Path is not a directory: {path}"
        raise NotADirectoryError(msg)
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


def get_ipackages() -> dict[str, str]:
    return get_installed_packages()


def get_ipkgs() -> list[str]:
    return get_installed_pkgs()


def hex2dec(s: str) -> int:
    return int(s, 16)


def hex_to_int(value: str) -> tuple[float, ...]:
    return tuple(int(value.lstrip("#")[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def hex_to_rgb(value: str) -> tuple[int, ...]:
    return tuple(int(value.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))


def is_python_file(path: (str | Path)) -> bool:
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


def _safe_cp(src: Path | str, dest: Path | str, no_clobber=True) -> bool:
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


def cpf(src: (str | Path), dest: (str | Path)) -> bool:
    return _safe_cp(src, dest)


def _safe_mv(src: Path | str, dest: Path | str, no_clobber=True) -> bool:
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


def move_file(src: (str | Path), dest: (str | Path)) -> bool:
    return _safe_mv(src, dest)


def format_size(sz: float) -> str:
    return fsz(sz)


def get_files_recursive(root: (str | Path), include_hidden: bool = True, ext: (list[str] | None) = None) -> list[Path]:
    root_path = Path(root).resolve()
    if not root_path.exists() or not root_path.is_dir():
        msg = "Invalid path"
        raise ValueError(msg)
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


def get_files_iter2(root: (str | Path), include_hidden: bool = True, ext: (list[str] | None) = None) -> Generator[Path]:
    from os import walk
    from os.path import join as path_join

    root = str(Path(root).resolve())
    extensions = tuple(ext) if ext else None
    for dirpath, dirnames, filenames in walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and (include_hidden or not d.startswith("."))]
        for filename in filenames:
            if not include_hidden and filename.startswith("."):
                continue
            full_path = path_join(dirpath, filename)
            if Path(full_path).is_symlink():
                continue
            if extensions is not None and not filename.endswith(extensions):
                continue
            yield Path(full_path).resolve()


def get_dirs_iter(path: (str | Path)):
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


def get_files_iter(path: (str | Path), ext: (list[str] | None) = None):
    path = Path(path)
    if not path.exists():
        msg = f"Path does not exist: {path}"
        raise FileNotFoundError(msg)
    if not path.is_dir():
        msg = f"Path is not a directory: {path}"
        raise NotADirectoryError(msg)
    if ext:
        ext = [(e.lower() if e.startswith(".") else f".{e.lower()}") for e in ext]
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


def gsz(path: (str | Path)) -> int:
    return get_size(path)


def ln(label) -> str:
    from shutil import get_terminal_size as _get_terminal_size

    ts = _get_terminal_size()[0]
    label_len = len(label) + 2
    chunk = (ts - label_len) // 2
    out = f"{'-' * chunk} {label} {'-' * chunk}"
    pad = ts - len(out)
    if pad > 0:
        out += "-" * pad
    return out


def oprint(text, color: str = "cyan", **kwargs) -> None:
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


def norm_str(sentence: str) -> str:
    from re import compile as re_compile

    alnum_regex = re_compile(r"(?ui)\W")
    string_out = alnum_regex.sub(" ", sentence)
    return string_out.strip().lower()


def prepend_text(path: (str | Path), prepend_text: str = ".min.") -> str:
    path = Path(path)
    if not path.suffix:
        msg = "The text argument expects a filename with an extension."
        raise ValueError(msg)
    new_filename = f"{path.stem}{prepend_text}{path.suffix[1:]}"
    if path.parent and path.parent != Path():
        return str(path.parent / new_filename)
    return new_filename


def get_files2(path: (str | Path), ext: (list[str] | None) = None) -> list[Path]:
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
                    files.extend(get_files2(Path(entry.path), ext))
    except OSError:
        pass
    return files


def get_dirz(path: (str | Path)) -> list[Path]:
    path = Path(path)
    dirs: list[Path] = []
    try:
        with os_scandir(path) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    dirs.append(Path(entry.path))
                    dirs.extend(get_dirz(Path(entry.path)))
    except OSError:
        pass
    return dirs


def get_files_rec(path):
    root = Path(path)
    files = []

    def collect_files(p: Path) -> None:
        try:
            with os_scandir(p) as it:
                for entry in it:
                    if entry.is_file():
                        files.append(Path(entry.path))
                    elif entry.is_dir(follow_symlinks=False):
                        collect_files(Path(entry.path))
        except OSError:
            pass

    collect_files(root)
    return files


# --- get_size ---
def get_size(path: str | Path) -> int:
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
            if not (fp := Path(root) / f).is_symlink():
                try:
                    total += fp.stat().st_size
                except OSError:
                    pass
    return total


# --- get_files ---
def get_files(path: str | Path, include_hidden: bool = True, ext: list[str] | None = None) -> list[Path]:
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
                        if entry.name not in SKIP_DIRS:
                            stack.append(entry)
                    elif entry.is_file(follow_symlinks=False):
                        if not include_hidden and entry.name.startswith("."):
                            continue
                        if ext is None or entry.name.endswith(ext):
                            files.append(entry)
        except (PermissionError, OSError):
            continue

    return sorted(files)


# --- get_pyfiles ---
def get_pyfiles(path: str | Path) -> list[Path]:
    path = Path(path)
    if path.is_file():
        if path.suffix == ".py":
            return [path]
        if not path.suffix and not path.name.startswith(".") and is_python_file(path):
            return [path]
        return []

    if not path.is_dir():
        return []

    pyfiles = []
    stack = [path]

    while stack:
        current = stack.pop()
        try:
            with os_scandir(current) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in SKIP_DIRS:
                            stack.append(entry)
                    elif entry.is_file(follow_symlinks=False):
                        p = Path(entry)
                        if p.suffix == ".py":
                            pyfiles.append(p)
                        elif not p.suffix and not p.name.startswith(".") and is_python_file(p):
                            pyfiles.append(p)
        except (PermissionError, OSError):
            continue

    return sorted(pyfiles)
