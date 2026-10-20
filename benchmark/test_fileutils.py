from __future__ import annotations
import atexit
import csv
import importlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import types

import pytest


_STUB_CONST = """
BIN_EXT = frozenset({".exe", ".bin", ".dll", ".so"})
TXT_EXT = frozenset({".txt", ".md", ".py", ".json"})
IMGEXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules"})
CHUNK_SIZE = 8192
THRESHOLD = 1024 * 1024
EMULATED = "/storage/emulated/0"
SDCARD = "/sdcard"
"""

_STUB_ISBINARY = """
from pathlib import Path


def is_binary(path):
    with Path(path).open("rb") as f:
        return b"\\0" in f.read(1024)
"""


def _load_module() -> types.ModuleType:
    name = os.environ.get("FILEUTILS_MODULE")
    if name:
        return importlib.import_module(name)
    try:
        return importlib.import_module("fu_pkg.fileutils")
    except ImportError:
        pass
    source = Path(os.environ.get("FILEUTILS_PATH", Path(__file__).with_name("fileutils.py")))
    root = Path(tempfile.mkdtemp(prefix="fu_"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    pkg = root / "fu_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "const.py").write_text(_STUB_CONST)
    (pkg / "isbinary.py").write_text(_STUB_ISBINARY)
    shutil.copy(source, pkg / "fileutils.py")
    sys.path.insert(0, str(root))
    return importlib.import_module("fu_pkg.fileutils")


fu = _load_module()

CAN_SYMLINK = hasattr(os, "symlink") and os.name != "nt"


def _file_len(path: Path) -> int:
    return len(path.name)


def _fail_on_bad(path: Path) -> int:
    if path.name == "bad.txt":
        raise RuntimeError("boom")
    return 1


def _write(path: Path, data: str | bytes = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data)
    return path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    _write(root / "a.py", "print(1)\n")
    _write(root / "b.txt", "bbb")
    _write(root / ".hidden.txt", "h")
    _write(root / "sub" / "c.py", "x = 1\n")
    _write(root / "sub" / "deep" / "d.txt", "ddddd")
    _write(root / ".git" / "x.py", "x = 2\n")
    _write(root / "__pycache__" / "y.pyc", "y")
    _write(root / "node_modules" / "z.js", "z")
    return root


def _rel(root: Path, paths) -> set[str]:
    return {Path(p).relative_to(root).as_posix() for p in paths}


FILTERED = {"a.py", "b.txt", ".hidden.txt", "sub/c.py", "sub/deep/d.txt"}
WALK_DEFAULT = FILTERED | {"node_modules/z.js"}


def test_read_lines_keepends(tmp_path):
    p = _write(tmp_path / "f.txt", "a\nb\n")
    assert fu.read_lines(p) == ["a\n", "b\n"]


def test_read_lines_strip_ends_keeps_trailing_empty(tmp_path):
    p = _write(tmp_path / "f.txt", "a\nb\n")
    assert fu.read_lines(p, ke=False) == ["a", "b", ""]


def test_read_lines_no_trailing_newline(tmp_path):
    p = _write(tmp_path / "f.txt", "a\nb")
    assert fu.read_lines(p, ke=False) == ["a", "b"]
    assert fu.read_lines(p, ke=True) == ["a\n", "b"]


def test_read_lines_empty_file(tmp_path):
    p = _write(tmp_path / "f.txt", "")
    assert fu.read_lines(p) == []
    assert fu.read_lines_mmap(p) == []


def test_read_lines_invalid_utf8_is_replaced(tmp_path):
    p = _write(tmp_path / "f.txt", b"ok\xff\n")
    assert fu.read_lines(p) == ["ok\ufffd\n"]


def test_read_lines_routes_large_files_to_mmap(tmp_path, monkeypatch):
    p = _write(tmp_path / "f.txt", "a\nb\n")
    monkeypatch.setattr(fu, "THRESHOLD", 0)
    monkeypatch.setattr(fu, "read_lines_mmap", lambda path, keep: ["sentinel"])
    assert fu.read_lines(p) == ["sentinel"]


def test_read_lines_mmap_matches_regular(tmp_path):
    p = _write(tmp_path / "f.txt", "one\r\ntwo\nthree\n")
    for keep in (True, False):
        assert fu.read_lines_mmap(p, keep) == fu.read_lines(p, keep)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("a.txt", ".txt"),
        ("a", ""),
        (".bashrc", ""),
        ("a.tar.gz", ".tar.gz"),
        ("a.tar.xz", ".tar.xz"),
        ("a.min.js", ".min.js"),
        ("a.b.c", ".c"),
        ("x.log.1", ".log.1"),
        ("archive.v2.tar.bz2", ".tar.bz2"),
    ],
)
def test_gext(name, expected):
    assert fu.gext(name) == expected
    assert fu.gext(Path(name)) == expected


def test_get_dirs(tree):
    dirs = _rel(tree, fu.get_dirs(tree))
    assert dirs == {".git", "__pycache__", "node_modules", "sub", "sub/deep"}


@pytest.mark.skipif(not CAN_SYMLINK, reason="symlinks unsupported")
def test_get_dirs_excludes_symlinks(tree):
    os.symlink(tree / "sub", tree / "link")
    assert "link" not in _rel(tree, fu.get_dirs(tree))


def test_get_dirs_non_directory(tmp_path):
    assert fu.get_dirs(tmp_path / "nope") == []
    assert fu.get_dirs(_write(tmp_path / "f.txt")) == []


def test_get_file_age_missing_and_dir(tmp_path):
    assert fu.get_file_age(tmp_path / "nope") == 0.0
    assert fu.get_file_age(tmp_path / "nope", True) == "0 sec"
    assert fu.get_file_age(tmp_path) == -1.0
    assert fu.get_file_age(tmp_path, True) == "0 sec"


def test_get_file_age_numeric(tmp_path):
    p = _write(tmp_path / "f.txt")
    age = fu.get_file_age(p)
    assert isinstance(age, float)
    assert -5 < age < 60


def test_get_file_age_string_format(tmp_path, monkeypatch):
    p = _write(tmp_path / "f.txt")
    ctime = p.stat().st_ctime
    monkeypatch.setattr(fu, "time", types.SimpleNamespace(time=lambda: ctime + 3661))
    assert fu.get_file_age(p, True) == "1 h, 1 min, 1 sec"
    monkeypatch.setattr(fu, "time", types.SimpleNamespace(time=lambda: ctime + 2 * 31536000 + 86400))
    assert fu.get_file_age(p, True) == "2 y, 1 d"
    monkeypatch.setattr(fu, "time", types.SimpleNamespace(time=lambda: ctime - 100))
    assert fu.get_file_age(p, True) == "0 sec"


def test_normalize_name():
    assert fu._normalize_name("Foo_Bar.baz--Qux") == "foo-bar-baz-qux"


def test_installed_packages():
    pkgs = fu.get_installed_packages()
    assert isinstance(pkgs, dict) and pkgs
    assert list(pkgs) == sorted(pkgs)
    assert all(k == k.lower() and "_" not in k and "." not in k for k in pkgs)
    names = fu.get_installed_pkgs()
    assert names == sorted(names)
    assert set(pkgs) <= set(names)


def test_get_mime_type():
    assert fu.get_mime_type("a.txt") == "text/plain"
    assert fu.get_mime_type(Path("a.png")) == "image/png"
    assert fu.get_mime_type("a.unknownext123") is None


def test_get_random_filename():
    name = fu.get_random_filename()
    assert len(name) == 10 and name.isalpha() and name.islower()
    assert len(fu.get_random_filename(25)) == 25
    assert fu.get_random_filename(0) == ""
    assert len({fu.get_random_filename(12) for _ in range(20)}) == 20


def test_is_image(tmp_path):
    assert fu.is_image(_write(tmp_path / "a.png"))
    assert not fu.is_image(_write(tmp_path / "a.txt"))
    assert not fu.is_image(tmp_path / "missing.png")
    (tmp_path / "dir.png").mkdir()
    assert not fu.is_image(tmp_path / "dir.png")


def test_is_within(tmp_path):
    child = tmp_path / "a" / "b"
    assert fu.is_within(child, tmp_path)
    assert fu.is_within(tmp_path, tmp_path)
    assert not fu.is_within(tmp_path, child)
    assert not fu.is_within(tmp_path / "a" / ".." / ".." / "x", tmp_path)
    assert fu.is_within(str(tmp_path / "a" / ".." / "b"), str(tmp_path))


def test_normalize_filename():
    assert fu.normalize_filename('a<b>:c"d/e\\f|g?h*i') == "a_b__c_d_e_f_g_h_i"
    assert fu.normalize_filename("tab\there") == "tab_here"
    assert fu.normalize_filename(Path("plain.txt")) == "plain.txt"


def test_normalize_path(tmp_path):
    assert fu.normalize_path(f"{fu.EMULATED}/DCIM/a.jpg") == Path(f"{fu.SDCARD}/DCIM/a.jpg")
    assert fu.normalize_path(tmp_path / "x" / ".." / "y") == (tmp_path / "y").resolve()


def test_reverse_dict_unique_values():
    assert fu.reverse_dict({"a": 1, "b": 2}) == {1: "a", 2: "b"}
    assert fu.reverse_dict({}) == {}


def test_reverse_dict_repeated_values():
    assert fu.reverse_dict({"a": 1, "b": 1, "c": 2}) == {1: ["a", "b"], 2: ["c"]}


@pytest.mark.parametrize(
    "size,expected",
    [
        (0, "0 B"),
        (1, "1 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1 << 20, "1.0 MB"),
        (5 * (1 << 30), "5.0 GB"),
        (1 << 40, "1.0 TB"),
        (1 << 50, "1024.0 TB"),
        (-2048, "2.0 KB"),
        (2048.9, "2.0 KB"),
    ],
)
def test_fsz(size, expected):
    assert fu.fsz(size) == expected


def test_safe_delete_file_and_dir(tmp_path):
    f = _write(tmp_path / "f.txt")
    assert fu.safe_delete(f) is True and not f.exists()
    d = tmp_path / "d"
    _write(d / "x" / "y.txt")
    assert fu.safe_delete(d) is True and not d.exists()


def test_safe_delete_missing(tmp_path):
    assert fu.safe_delete(tmp_path / "nope") is False


@pytest.mark.skipif(not CAN_SYMLINK, reason="symlinks unsupported")
def test_safe_delete_symlink_keeps_target(tmp_path):
    target = tmp_path / "target"
    _write(target / "keep.txt")
    link = tmp_path / "link"
    os.symlink(target, link)
    assert fu.safe_delete(link) is True
    assert not link.is_symlink()
    assert (target / "keep.txt").exists()


def test_get_filez(tree):
    assert _rel(tree, fu.get_filez(tree)) == FILTERED
    assert _rel(tree, fu.get_filez(tree, [".py"])) == {"a.py", "sub/c.py"}
    assert _rel(tree, fu.get_filez(str(tree), [".txt"])) == {"b.txt", ".hidden.txt", "sub/deep/d.txt"}


@pytest.mark.skipif(not CAN_SYMLINK, reason="symlinks unsupported")
def test_get_filez_skips_symlinked_files(tree):
    os.symlink(tree / "a.py", tree / "link.py")
    assert "link.py" not in _rel(tree, fu.get_filez(tree))


def test_unique_path_free_name(tmp_path):
    p = tmp_path / "a.txt"
    assert fu.unique_path(p) == p


def test_unique_path_increments(tmp_path):
    p = _write(tmp_path / "a.txt")
    assert fu.unique_path(p) == tmp_path / "a_1.txt"
    _write(tmp_path / "a_1.txt")
    assert fu.unique_path(p) == tmp_path / "a_2.txt"
    assert fu.unique_path(tmp_path / "a_1.txt") == tmp_path / "a_2.txt"


def test_unique_path_multipart_suffix(tmp_path):
    p = _write(tmp_path / "pack.tar.gz")
    assert fu.unique_path(p) == tmp_path / "pack_1.tar.gz"


def test_unique_path_strips_stale_counter(tmp_path):
    assert fu.unique_path(tmp_path / "a_7.txt") == tmp_path / "a.txt"


def test_unique_path_no_extension(tmp_path):
    p = _write(tmp_path / "README")
    assert fu.unique_path(str(p)) == tmp_path / "README_1"


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "0s"),
        (-5, "0s"),
        (0.0005, "500µs"),
        (0.5, "500.00ms"),
        (5, "5s"),
        (90, "1m, 30s"),
        (120, "2m"),
        (3600, "1h"),
        (3661, "1h, 1m, 1s"),
        (86400, "1d"),
        (90000, "1d, 1h"),
        (90060, "1d, 1h, 1m"),
        (2592000 * 2, "2.00 months"),
    ],
)
def test_format_time(seconds, expected):
    assert fu.format_time(seconds) == expected


def test_runcmd_captures_output(capsys):
    code, out, err = fu.runcmd([sys.executable, "-c", "import sys; print('hi'); print('e', file=sys.stderr)"])
    assert code == 0 and out.strip() == "hi" and err.strip() == "e"
    assert "hi" in capsys.readouterr().out


def test_runcmd_quiet_variants(capsys):
    assert fu.runcmd([sys.executable, "-c", "print('x')"], run_silently=True) == (0, "", "")
    code, out, _ = fu.runcmd([sys.executable, "-c", "print('x')"], show_output=False)
    assert code == 0 and out.strip() == "x"
    assert capsys.readouterr().out == ""


def test_runcmd_exit_code():
    assert fu.runcmd([sys.executable, "-c", "raise SystemExit(3)"], show_output=False)[0] == 3


def test_runcmd_missing_command():
    code, out, err = fu.runcmd(["definitely-not-a-real-command-xyz"], show_output=False)
    assert code == 127 and out == "" and "not found" in err


def test_runcmd_timeout():
    code, _, err = fu.runcmd([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.3, show_output=False)
    assert code == 124 and "timed out" in err


def test_runcmd_empty_command():
    with pytest.raises(ValueError):
        fu.runcmd([])


def test_write_txt_file(tmp_path):
    p = tmp_path / "new" / "dir" / "f.txt"
    assert fu.write_txt_file(p, "one") is True
    assert p.read_text() == "one"
    assert fu.write_txt_file(p, "two") is False
    assert p.read_text() == "one"
    assert fu.write_txt_file(p, "two", overwrite=True) is True
    assert p.read_text() == "two"
    assert fu.write_txt_file(p, 123) is False  # type: ignore[arg-type]


def test_should_skip(tmp_path):
    assert fu.should_skip(tmp_path / ".git" / "config")
    assert fu.should_skip("a/__pycache__/b.pyc")
    assert not fu.should_skip(_write(tmp_path / "ok" / "f.txt"))


@pytest.mark.skipif(not CAN_SYMLINK, reason="symlinks unsupported")
def test_should_skip_symlink(tmp_path):
    t = _write(tmp_path / "t.txt")
    os.symlink(t, tmp_path / "l.txt")
    assert fu.should_skip(tmp_path / "l.txt")


def test_append_text(tmp_path):
    p = tmp_path / "f.txt"
    assert fu.append_text(p, "a") is True
    assert fu.append_text(p, "b") is True
    assert p.read_text() == "a\nb"
    assert fu.append_text(tmp_path, "x") is False


@pytest.mark.skipif(not CAN_SYMLINK, reason="symlinks unsupported")
def test_append_text_rejects_symlink(tmp_path):
    t = _write(tmp_path / "t.txt", "t")
    os.symlink(t, tmp_path / "l.txt")
    assert fu.append_text(tmp_path / "l.txt", "x") is False
    assert t.read_text() == "t"


def test_get_removed_lines():
    assert fu.get_removed_lines("a\nb\nb\nc\n\n", "b\n") == ["a", "c"]
    assert fu.get_removed_lines("a\nb", "a\nb") == []
    assert fu.get_removed_lines("", "a") == []
    assert set(fu.get_removed_lines("a\nb", "")) == {"a", "b"}


def test_restore_bak(tmp_path):
    p = _write(tmp_path / "f.txt", "new")
    _write(tmp_path / "f.txt.bak", "old")
    assert fu.restore_bak(p) is True
    assert p.read_text() == "old"
    assert not (tmp_path / "f.txt.bak").exists()
    assert fu.restore_bak(p) is False


def test_rrs_no_change(capsys):
    fu.rrs(Path("x.txt"), 10, 10)
    out = capsys.readouterr().out
    assert "x.txt" in out and "NO CHANGE" in out


def test_rrs_change_and_zero_before(capsys):
    fu.rrs(Path("x.txt"), 2048, 1024)
    out = capsys.readouterr().out
    assert "2048->1024" in out and "1.0 KB" in out and "50.0" in out
    fu.rrs(Path("y.txt"), 0, 10)
    assert "y.txt" in capsys.readouterr().out


def test_is_empty(tmp_path):
    assert fu.is_empty(tmp_path) is True
    _write(tmp_path / "f.txt")
    assert fu.is_empty(tmp_path) is False
    assert fu.is_empty(tmp_path / "f.txt") is False
    assert fu.is_empty(tmp_path / "missing") is False


def test_get_files_scandir(tree):
    assert _rel(tree, fu.get_files_scandir(tree)) == FILTERED
    assert _rel(tree, fu.get_files_scandir(tree, include_hidden=False)) == FILTERED - {".hidden.txt"}
    assert _rel(tree, fu.get_files_scandir(tree, ext=[".py"])) == {"a.py", "sub/c.py"}
    result = fu.get_files_scandir(tree)
    assert result == sorted(result)


def test_get_files_scandir_multipart_ext(tmp_path):
    _write(tmp_path / "a.tar.gz")
    _write(tmp_path / "b.gz")
    assert _rel(tmp_path, fu.get_files_scandir(tmp_path, ext=[".tar.gz"])) == {"a.tar.gz"}


def test_get_files_scandir_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        fu.get_files_scandir(tmp_path / "nope")
    with pytest.raises(NotADirectoryError):
        fu.get_files_scandir(_write(tmp_path / "f.txt"))


def test_get_files4_matches_scandir(tree):
    assert fu.get_files4(tree, False, [".txt"]) == fu.get_files_scandir(tree, False, [".txt"])
    with pytest.raises(FileNotFoundError):
        fu.get_files4(tree / "nope")


def test_get_fast(tree):
    assert _rel(tree, fu.get_fast(tree)) == FILTERED
    assert _rel(tree, fu.get_fast(str(tree), [".txt"])) == {"b.txt", ".hidden.txt", "sub/deep/d.txt"}


def test_get_files_iter_includes_skip_dirs_and_resolves(tree):
    got = list(fu.get_files_iter(tree))
    assert all(p.is_absolute() for p in got)
    rel = _rel(tree.resolve(), got)
    assert FILTERED <= rel
    assert {".git/x.py", "node_modules/z.js"} <= rel
    assert _rel(tree.resolve(), fu.get_files_iter(tree, [".js"])) == {"node_modules/z.js"}


def test_get_files_iter_requires_directory(tmp_path):
    with pytest.raises(NotADirectoryError):
        fu.get_files_iter(tmp_path / "nope")


def test_get_files(tree):
    result = fu.get_files(tree)
    assert _rel(tree, result) == FILTERED and result == sorted(result)
    assert _rel(tree, fu.get_files(tree, [".py"])) == {"a.py", "sub/c.py"}
    assert fu.get_files(tree, []) == []
    assert fu.get_files(tree / "nope") == []


def test_getfiles_respects_ext(tree):
    assert _rel(tree, fu.getfiles(tree)) == FILTERED
    assert _rel(tree, fu.getfiles(tree, [".txt"])) == {"b.txt", ".hidden.txt", "sub/deep/d.txt"}


def test_get_files_pathlib_is_case_insensitive_on_suffix(tree):
    _write(tree / "UP.PY")
    assert _rel(tree, fu.get_files_pathlib(tree, ext=[".py"])) == {"a.py", "sub/c.py", "UP.PY"}
    assert ".hidden.txt" not in _rel(tree, fu.get_files_pathlib(tree, include_hidden=False))
    with pytest.raises(FileNotFoundError):
        fu.get_files_pathlib(tree / "nope")


def test_get_nobinary(tree):
    _write(tree / "blob.dat", b"\x00\x01\x02")
    result = _rel(tree, fu.get_nobinary(tree))
    assert "blob.dat" not in result
    assert FILTERED <= result


def test_is_python_file_cases(tmp_path):
    assert fu.is_python_file(_write(tmp_path / "a.py", "x = 1\n"))
    assert not fu.is_python_file(_write(tmp_path / "empty.py", ""))
    assert not fu.is_python_file(_write(tmp_path / "a.txt", "x = 1\n"))
    assert fu.is_python_file(_write(tmp_path / "script", "#!/usr/bin/env python3\nprint(1)\n"))
    assert fu.is_python_file(_write(tmp_path / "noext", "x = 1\n"))
    assert not fu.is_python_file(_write(tmp_path / "readme", "hello world\n"))
    assert not fu.is_python_file(_write(tmp_path / "blob", b"\x00\x01\x02\x03"))
    assert not fu.is_python_file(tmp_path)
    assert not fu.is_python_file(tmp_path / "missing.py")
    assert not fu.is_python_file(_write(tmp_path / "bin.py", b"\x00\x01\x02"))


def test_get_pyfiles_single_file(tmp_path):
    py = _write(tmp_path / "a.py", "x = 1\n")
    assert fu.get_pyfiles(py) == [py]
    assert fu.get_pyfiles(_write(tmp_path / "b.txt")) == []
    assert fu.get_pyfiles(_write(tmp_path / "tool", "#!/usr/bin/python\n")) == [tmp_path / "tool"]
    assert fu.get_pyfiles(tmp_path / "missing") == []


def test_get_pyfiles_directory(tree):
    _write(tree / "tool", "#!/usr/bin/env python\nprint(1)\n")
    _write(tree / "README", "just words\n")
    _write(tree / ".hiddenscript", "#!/usr/bin/env python\n")
    result = fu.get_pyfiles(tree)
    assert _rel(tree, result) == {"a.py", "sub/c.py", "tool"}
    assert result == sorted(result)


def test_get_pyfiles_iter(tree):
    _write(tree / "tool", "#!/usr/bin/env python\nprint(1)\n")
    got = _rel(tree, fu.get_pyfiles_iter(tree))
    assert got == {"a.py", "sub/c.py", "tool"}


def test_gsz(tree, tmp_path):
    assert fu.gsz(tree / "b.txt") == 3
    assert fu.gsz(tree / "sub") == len("x = 1\n") + 5
    assert fu.gsz(str(tree / "b.txt")) == 3
    assert fu.gsz(tmp_path / "missing") == 0
    assert fu.gsz(123) == 0  # type: ignore[arg-type]
    assert fu.gsz(None) == 0  # type: ignore[arg-type]


@pytest.mark.skipif(not CAN_SYMLINK, reason="symlinks unsupported")
def test_gsz_ignores_symlinks(tree):
    os.symlink(tree / "b.txt", tree / "link.txt")
    os.symlink(tree / "sub", tree / "linkdir")
    assert fu.gsz(tree / "link.txt") == 0
    assert fu.gsz(tree / "linkdir") == 0
    total = fu.gsz(tree)
    (tree / "link.txt").unlink()
    (tree / "linkdir").unlink()
    assert fu.gsz(tree) == total


def test_gsze(tree):
    everything = sum(p.stat().st_size for p in tree.rglob("*") if p.is_file())
    assert fu.gsze(tree) == everything
    assert fu.gsze(tree, [".txt"]) == 3 + 1 + 5
    assert fu.gsze(tree, [".TXT"]) == 3 + 1 + 5
    _write(tree / "UP.TXT", "12")
    assert fu.gsze(tree, [".txt"]) == 3 + 1 + 5 + 2
    assert fu.gsze(tree / "missing") == 0


def test_copy_dir(tree, tmp_path):
    (tree / "emptydir").mkdir()
    dest = tmp_path / "dest"
    assert fu.copy_dir(str(tree), str(dest)) is True
    out = dest / "root"
    for rel in FILTERED | {".git/x.py", "node_modules/z.js"}:
        assert (out / rel).read_text() == (tree / rel).read_text()
    assert (out / "emptydir").is_dir()
    assert (tree / "a.py").exists()


def test_copy_dir_many_files(tmp_path):
    src = tmp_path / "src"
    for i in range(60):
        _write(src / f"d{i % 5}" / f"f{i}.txt", str(i))
    assert fu.copy_dir(str(src), str(tmp_path / "out")) is True
    copied = sorted(p.name for p in (tmp_path / "out" / "src").rglob("*.txt"))
    assert copied == sorted(f"f{i}.txt" for i in range(60))


def test_copy_dir_failures(tmp_path, capsys):
    assert fu.copy_dir(str(tmp_path / "missing"), str(tmp_path / "d")) is False
    assert "Copy failed" in capsys.readouterr().out
    assert fu.copy_dir(str(_write(tmp_path / "f.txt")), str(tmp_path / "d")) is False


def test_copy_dir_empty_source(tmp_path):
    (tmp_path / "empty").mkdir()
    assert fu.copy_dir(str(tmp_path / "empty"), str(tmp_path / "d")) is True
    assert (tmp_path / "d" / "empty").is_dir()


def test_move_dir(tree, tmp_path):
    dest = tmp_path / "dest"
    assert fu.move_dir(str(tree), str(dest)) is True
    assert not tree.exists()
    assert (dest / "root" / "sub" / "deep" / "d.txt").read_text() == "ddddd"


def test_move_dir_into_empty_existing_destination(tree, tmp_path):
    (tmp_path / "dest" / "root").mkdir(parents=True)
    assert fu.move_dir(str(tree), str(tmp_path / "dest")) is True
    assert (tmp_path / "dest" / "root" / "a.py").exists()


def test_move_dir_refuses_non_empty_destination(tree, tmp_path, capsys):
    _write(tmp_path / "dest" / "root" / "existing.txt")
    assert fu.move_dir(str(tree), str(tmp_path / "dest")) is False
    assert "not empty" in capsys.readouterr().out
    assert (tree / "a.py").exists()


def test_move_dir_refuses_moving_into_itself(tree):
    assert fu.move_dir(str(tree), str(tree / "inner")) is False
    assert (tree / "a.py").exists()


def test_move_dir_falls_back_to_copy_when_rename_fails(tree, tmp_path, monkeypatch):
    def broken(self, target):
        raise OSError("cross-device")

    monkeypatch.setattr(Path, "rename", broken)
    dest = tmp_path / "dest"
    assert fu.move_dir(str(tree), str(dest)) is True
    assert not tree.exists()
    assert (dest / "root" / "sub" / "c.py").read_text() == "x = 1\n"


def test_move_dir_errors(tmp_path, capsys):
    assert fu.move_dir(str(tmp_path / "missing"), str(tmp_path / "d")) is False
    assert "Move failed" in capsys.readouterr().out
    assert fu.move_dir(str(_write(tmp_path / "f.txt")), str(tmp_path / "d")) is False


def test_file_walker_config_defaults_are_independent():
    a, b = fu.FileWalkerConfig(), fu.FileWalkerConfig()
    a.skip_dirs.add("x")
    assert "x" not in b.skip_dirs
    assert a.skip_symlinks is True and a.max_depth == 999 and a.exclude_pattern == "lazy"


def test_walk_config_default(tree):
    _write(tree / "lazy")
    assert _rel(tree.resolve(), fu.get_files_iter_config(tree)) == WALK_DEFAULT


def test_walk_config_patterns(tree):
    cfg = fu.FileWalkerConfig(file_pattern="*.py", exclude_pattern=None)
    assert _rel(tree.resolve(), fu.get_files_iter_config(tree, cfg)) == {"a.py", "sub/c.py"}
    cfg = fu.FileWalkerConfig(exclude_pattern="*.txt")
    assert _rel(tree.resolve(), fu.get_files_iter_config(tree, cfg)) == {"a.py", "sub/c.py", "node_modules/z.js"}


def test_walk_config_skip_hidden(tree):
    cfg = fu.FileWalkerConfig(skip_hidden=True)
    assert _rel(tree.resolve(), fu.get_files_iter_config(tree, cfg)) == WALK_DEFAULT - {".hidden.txt"}


def test_walk_config_max_depth(tree):
    root = tree.resolve()
    assert _rel(root, fu.get_files_iter_config(tree, fu.FileWalkerConfig(max_depth=1))) == {
        "a.py",
        "b.txt",
        ".hidden.txt",
    }
    assert _rel(root, fu.get_files_iter_config(tree, fu.FileWalkerConfig(max_depth=2))) == WALK_DEFAULT - {
        "sub/deep/d.txt"
    }
    assert list(fu.get_files_iter_config(tree, fu.FileWalkerConfig(max_depth=0))) == []


def test_walk_config_custom_skip_dirs(tree):
    cfg = fu.FileWalkerConfig(skip_dirs={"sub"})
    got = _rel(tree.resolve(), fu.get_files_iter_config(tree, cfg))
    assert "sub/c.py" not in got and ".git/x.py" in got


def test_walk_config_file_filter(tree):
    got = _rel(tree.resolve(), fu.get_files_iter_config(tree, file_filter=lambda p: p.suffix == ".py"))
    assert got == {"a.py", "sub/c.py"}


def test_walk_config_single_file(tree):
    assert list(fu.get_files_iter_config(tree / "a.py")) == [(tree / "a.py").resolve()]
    cfg = fu.FileWalkerConfig(skip_hidden=True)
    assert list(fu.get_files_iter_config(tree / ".hidden.txt", cfg)) == []
    assert list(fu.get_files_iter_config(tree / "a.py", file_filter=lambda p: False)) == []


def test_walk_config_missing_path_warns(tmp_path, capsys):
    assert list(fu.get_files_iter_config(tmp_path / "nope")) == []
    assert "does not exist" in capsys.readouterr().out


@pytest.mark.skipif(not CAN_SYMLINK, reason="symlinks unsupported")
def test_walk_config_symlink_handling(tree):
    os.symlink(tree / "a.py", tree / "link.py")
    assert "link.py" not in _rel(tree.resolve(), fu.get_files_iter_config(tree))
    cfg = fu.FileWalkerConfig(skip_symlinks=False)
    assert "link.py" in _rel(tree.resolve(), fu.get_files_iter_config(tree, cfg))


def _sample_report(n_success: int = 7) -> fu.ReportGenerator:
    rep = fu.ReportGenerator("My Report", width=40)
    for i in range(n_success):
        rep.add_item(fu.ReportItem(f"/p/{i}.txt", "success", f"ok {i}"))
    rep.add_item(fu.ReportItem("/p/bad.txt", "error", "broken"))
    rep.add_item(fu.ReportItem("/p/blob.bin", "binary"))
    rep.add_item(fu.ReportItem("/p/other", "unknown-category"))
    return rep


def test_report_item_defaults():
    before = time.time()
    item = fu.ReportItem("p", "info")
    assert item.message == "" and item.details == {} and item.timestamp >= before
    assert fu.ReportItem("p", "info").details is not item.details


def test_report_stats():
    rep = _sample_report()
    assert rep.stats["success"] == 7 and rep.stats["error"] == 1 and rep.stats["binary"] == 1
    rep.add_stat("files_scanned", 99)
    assert rep.stats["files_scanned"] == 99


def test_report_print_truncates_by_default(capsys):
    _sample_report().print_report()
    out = capsys.readouterr().out
    assert "My Report" in out and "Summary:" in out
    assert "Success: 7" in out and "... and 2 more" in out
    assert "/p/bad.txt" in out and "broken" in out
    assert "unknown-category" not in out and "/p/other" not in out
    assert "Files Scanned" not in out


def test_report_print_show_all(capsys):
    rep = _sample_report()
    rep.add_stat("files_scanned", 1234)
    rep.print_report(show_all=True)
    out = capsys.readouterr().out
    assert "more" not in out and "/p/6.txt" in out
    assert "Files Scanned" in out and "1,234" in out


def test_report_sorting(capsys):
    rep = fu.ReportGenerator()
    rep.add_item(fu.ReportItem("/z", "success"))
    rep.add_item(fu.ReportItem("/a", "success"))
    rep.print_report(sort_by="path")
    assert [i.path for i in rep.items] == ["/a", "/z"]
    rep.items[0].timestamp = 10**10
    rep.print_report(sort_by="time")
    assert [i.path for i in rep.items] == ["/z", "/a"]
    rep.print_report(sort_by="category")
    capsys.readouterr()


def test_report_export_text(tmp_path):
    rep = _sample_report(2)
    target = tmp_path / "r.txt"
    rep.export_to_file(target)
    text = target.read_text()
    assert text.startswith("My Report\n" + "=" * 40)
    assert "[SUCCESS] /p/0.txt - ok 0" in text and "[BINARY] /p/blob.bin\n" in text
    assert "Summary:" in text and "  success: 2" in text


def test_report_export_csv(tmp_path):
    rep = _sample_report(2)
    target = tmp_path / "r.csv"
    rep.export_to_file(target, format="csv")
    with target.open(newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Path", "Category", "Message", "Timestamp"]
    assert len(rows) == 1 + 5
    assert rows[1][:3] == ["/p/0.txt", "success", "ok 0"]
    assert "T" in rows[1][3]


def test_report_export_unknown_format_is_noop(tmp_path):
    target = tmp_path / "r.out"
    _sample_report().export_to_file(target, format="xml")
    assert not target.exists()


def test_remove_blank_lines():
    assert fu.remove_blank_lines("a\n\n\n\nb\n") == "a\n\nb\n"
    assert fu.remove_blank_lines("a\n  \n\t\nb") == "a\n  \nb"
    assert fu.remove_blank_lines("") == ""
    assert fu.remove_blank_lines("a\nb\n") == "a\nb\n"


def test_walk_paths_file_dir_and_list(tree):
    assert list(fu.walk_paths(tree / "a.py")) == [tree / "a.py"]
    assert list(fu.walk_paths(str(tree / "a.py"), [".txt"])) == []
    assert _rel(tree, fu.walk_paths(tree)) == FILTERED
    got = _rel(tree, fu.walk_paths([tree / "a.py", tree / "sub"], [".py"]))
    assert got == {"a.py", "sub/c.py"}


def test_walk_paths_glob(tree):
    assert _rel(tree, fu.walk_paths(str(tree / "*.py"))) == {"a.py"}
    assert _rel(tree, fu.walk_paths(str(tree / "*" / "c.py"))) == {"sub/c.py"}
    assert _rel(tree, fu.walk_paths(str(tree / "su*"), [".py"])) == {"sub/c.py"}
    assert _rel(tree, fu.walk_paths(str(tree / "*.txt"), [".py"])) == set()


def test_walk_paths_missing_without_glob(tmp_path):
    assert list(fu.walk_paths(tmp_path / "missing" / "file.txt")) == []


def test_worker_success_and_failure(tmp_path):
    good = _write(tmp_path / "ok.txt")
    assert fu.worker(good, _file_len) == (good, len("ok.txt"))
    bad = _write(tmp_path / "bad.txt")
    path, result = fu.worker(bad, _fail_on_bad)
    assert path == bad and result == "ERROR: boom"


def test_process_files(tmp_path):
    files = [_write(tmp_path / f"file{i}.txt") for i in range(10)]
    results = dict(fu.process_files(iter(files), _file_len, max_workers=2, prefetch=4))
    assert results == {f: len(f.name) for f in files}


def test_process_files_empty():
    assert list(fu.process_files(iter([]), _file_len, max_workers=1)) == []


def test_main_func(tmp_path, capsys):
    _write(tmp_path / "a.txt")
    _write(tmp_path / "b.txt")
    _write(tmp_path / "bad.txt")
    fu.main_func(tmp_path, _fail_on_bad, max_workers=2, prefetch=2)
    out = capsys.readouterr().out
    assert "3 files processed, 1 errors" in out and "✗" in out and "✓" in out
    fu.main_func(tmp_path, _fail_on_bad, ext=[".nope"], max_workers=1, verbose=False)
    assert capsys.readouterr().out == ""


def test_is_text_file_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        fu.is_text_file(tmp_path / "missing.txt")
    with pytest.raises(ValueError):
        fu.is_text_file(tmp_path)


def test_is_text_file_by_extension(tmp_path):
    assert fu.is_text_file(_write(tmp_path / "a.exe", "plain text")) is False
    assert fu.is_text_file(_write(tmp_path / "a.txt", b"\x00\x00\x00")) is True


def test_is_text_file_by_content(tmp_path):
    assert fu.is_text_file(_write(tmp_path / "a.weird", "hello world\n" * 10)) is True
    assert fu.is_text_file(_write(tmp_path / "b.weird", "Привет мир, это текст\n" * 20)) is True
    assert fu.is_text_file(_write(tmp_path / "c.weird", b"\x00\x01\x02" * 50)) is False
    assert fu.is_text_file(_write(tmp_path / "d.weird", bytes(range(256)) * 4)) is False
    assert fu.is_text_file(_write(tmp_path / "e.weird", "")) is True


def test_check_binary_chunk():
    assert fu._check_binary_chunk(b"") is False
    assert fu._check_binary_chunk(b"plain ascii text") is False
    assert fu._check_binary_chunk(b"\x00" * 10) is True
    assert fu._check_binary_chunk(b"a" * 98 + b"\x00\x00") is False
    assert fu._check_binary_chunk(b"a" * 100 + b"\x00" * 20) is True
    truncated_utf8 = "é".encode() * 40 + "é".encode()[:1]
    assert fu._check_binary_chunk(truncated_utf8) is False


def test_atomic_write(tmp_path):
    p = tmp_path / "f.txt"
    fu.atomic_write(p, "one")
    assert p.read_text() == "one"
    fu.atomic_write(p, "two ✓")
    assert p.read_text(encoding="utf-8") == "two ✓"
    assert [x.name for x in tmp_path.iterdir()] == ["f.txt"]


def test_atomic_write_cleans_up_on_failure(tmp_path, monkeypatch):
    p = _write(tmp_path / "f.txt", "orig")

    def broken(self, target):
        raise OSError("nope")

    monkeypatch.setattr(Path, "replace", broken)
    with pytest.raises(OSError):
        fu.atomic_write(p, "new")
    monkeypatch.undo()
    assert p.read_text() == "orig"
    assert [x.name for x in tmp_path.iterdir()] == ["f.txt"]


def test_walk_files_and_walkfiles(tree):
    assert _rel(tree, fu.walk_files(tree)) == FILTERED
    assert _rel(tree, fu.walk_files(tree, [".py"])) == {"a.py", "sub/c.py"}
    assert isinstance(fu.walk_files(tree), list)
    gen = fu.walkfiles(tree, [".txt"])
    assert not isinstance(gen, list)
    assert _rel(tree, gen) == {"b.txt", ".hidden.txt", "sub/deep/d.txt"}


@pytest.mark.skipif(not CAN_SYMLINK, reason="symlinks unsupported")
def test_walk_files_skips_symlinks(tree):
    os.symlink(tree / "a.py", tree / "link.py")
    os.symlink(tree / "sub", tree / "linkdir")
    got = _rel(tree, fu.walk_files(tree))
    assert "link.py" not in got and not any(g.startswith("linkdir") for g in got)
