# tests/test_fileutils.py
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest import mock

import pytest

from dh import (
    append_text,
    atomic_write,
    fsz,
    gext,
    get_dirs,
    get_fast,
    get_file_age,
    get_files,
    get_files4,
    get_files_iter,
    get_files_iter_config,
    get_files_pathlib,
    get_files_scandir,
    get_installed_packages,
    get_installed_pkgs,
    get_mime_type,
    get_nobinary,
    get_pyfiles,
    get_pyfiles_iter,
    get_random_filename,
    get_removed_lines,
    getfiles,
    gsz,
    is_empty,
    is_image,
    is_python_file,
    is_text_file,
    is_within,
    normalize_filename,
    normalize_path,
    read_lines,
    remove_blank_lines,
    restore_bak,
    reverse_dict,
    rrs,
    runcmd,
    safe_delete,
    should_skip,
    unique_path,
    walk_files,
    walk_paths,
    walkfiles,
    write_txt_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    """Create a small directory tree for testing."""
    (tmp_path / "a.txt").write_text("hello\nworld\n")
    (tmp_path / "b.py").write_text("print('hi')\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_text("nested\n")
    (tmp_path / "sub" / "d.bin").write_bytes(b"\x00\x01\x02\x03")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "e.pyc").write_bytes(b"\x00\x00")
    return tmp_path


@pytest.fixture
def binary_file(tmp_path: Path) -> Path:
    p = tmp_path / "blob.bin"
    p.write_bytes(bytes(range(256)) * 10)
    return p


@pytest.fixture
def text_file(tmp_path: Path) -> Path:
    p = tmp_path / "text.txt"
    p.write_text("line1\nline2\nline3\n")
    return p


# ---------------------------------------------------------------------------
# read_lines
# ---------------------------------------------------------------------------


class TestReadLines:
    def test_small_file_keep_ends(self, text_file: Path):
        lines = read_lines(text_file, ke=True)
        assert lines == ["line1\n", "line2\n", "line3\n"]

    def test_small_file_no_keep_ends(self, text_file: Path):
        lines = read_lines(text_file, ke=False)
        assert lines == ["line1", "line2", "line3"]

    def test_trailing_newline_preserved(self, tmp_path: Path):
        p = tmp_path / "t.txt"
        p.write_bytes(b"a\nb\n")
        lines = read_lines(p, ke=True)
        assert lines == ["a\n", "b\n"]

    def test_empty_file(self, tmp_path: Path):
        p = tmp_path / "empty.txt"
        p.write_bytes(b"")
        lines = read_lines(p)
        assert lines == []

    def test_large_file_uses_mmap(self, tmp_path: Path, monkeypatch):
        # Force the mmap branch
        monkeypatch.setattr("fileutils.THRESHOLD", 0)
        p = tmp_path / "big.txt"
        p.write_text("x\ny\nz\n")
        lines = read_lines(p, ke=True)
        assert lines == ["x\n", "y\n", "z\n"]


# ---------------------------------------------------------------------------
# gext
# ---------------------------------------------------------------------------


class TestGext:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("file.txt", ".txt"),
            ("file.tar.gz", ".tar.gz"),
            ("file.tar.xz", ".tar.xz"),
            ("file.tar.bz2", ".tar.bz2"),
            ("archive.tar", ".tar"),
            ("app.min.js", ".min.js"),
            ("noext", ""),
            ("file.py", ".py"),
        ],
    )
    def test_extensions(self, name: str, expected: str):
        assert gext(name) == expected


# ---------------------------------------------------------------------------
# get_dirs
# ---------------------------------------------------------------------------


class TestGetDirs:
    def test_finds_subdirs(self, sample_tree: Path):
        dirs = get_dirs(sample_tree)
        names = {d.name for d in dirs}
        assert "sub" in names
        assert "__pycache__" in names

    def test_non_directory_returns_empty(self, text_file: Path):
        assert get_dirs(text_file) == []


# ---------------------------------------------------------------------------
# get_file_age
# ---------------------------------------------------------------------------


class TestGetFileAge:
    def test_nonexistent_returns_zero(self, tmp_path: Path):
        assert get_file_age(tmp_path / "nope") == 0.0
        assert get_file_age(tmp_path / "nope", str_mode=True) == "0 sec"

    def test_fresh_file_age_is_small(self, text_file: Path):
        age = get_file_age(text_file)
        assert isinstance(age, float)
        assert 0 <= age < 5

    def test_str_mode(self, text_file: Path):
        result = get_file_age(text_file, str_mode=True)
        assert isinstance(result, str)
        assert result.endswith("sec") or "sec" in result

    def test_directory_returns_sentinel(self, tmp_path: Path):
        assert get_file_age(tmp_path) == -1.0
        assert get_file_age(tmp_path, str_mode=True) == "0 sec"


# ---------------------------------------------------------------------------
# installed packages
# ---------------------------------------------------------------------------


class TestInstalledPackages:
    def test_returns_dict(self):
        pkgs = get_installed_packages()
        assert isinstance(pkgs, dict)

    def test_returns_list(self):
        pkgs = get_installed_pkgs()
        assert isinstance(pkgs, list)


# ---------------------------------------------------------------------------
# MIME / random
# ---------------------------------------------------------------------------


class TestMimeAndRandom:
    def test_mime_type(self):
        assert get_mime_type("a.txt") == "text/plain"

    def test_random_filename_length(self):
        assert len(get_random_filename(20)) == 20

    def test_random_filename_is_alpha(self):
        name = get_random_filename(50)
        assert name.isalpha()


# ---------------------------------------------------------------------------
# is_image / is_within
# ---------------------------------------------------------------------------


class TestIsImage:
    def test_png(self, tmp_path: Path):
        p = tmp_path / "x.png"
        p.write_bytes(b"\x89PNG")
        assert is_image(p) is True

    def test_text_not_image(self, text_file: Path):
        assert is_image(text_file) is False

    def test_missing(self, tmp_path: Path):
        assert is_image(tmp_path / "missing.png") is False


class TestIsWithin:
    def test_child_inside_parent(self, tmp_path: Path):
        child = tmp_path / "a" / "b.txt"
        child.parent.mkdir()
        child.touch()
        assert is_within(child, tmp_path) is True

    def test_outside(self, tmp_path: Path):
        other = tmp_path.parent / "elsewhere"
        assert is_within(other, tmp_path) is False


# ---------------------------------------------------------------------------
# normalize_filename / normalize_path
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_special_chars(self):
        result = normalize_filename('a<b>c:d"e/f\\g|h?i*j')
        assert "<" not in result and ">" not in result
        assert ":" not in result and "/" not in result

    def test_normalize_path_resolves(self, tmp_path: Path):
        p = normalize_path(tmp_path)
        assert p == tmp_path.resolve()


# ---------------------------------------------------------------------------
# reverse_dict
# ---------------------------------------------------------------------------


class TestReverseDict:
    def test_simple(self):
        assert reverse_dict({"a": 1, "b": 2}) == {1: "a", 2: "b"}

    def test_duplicate_values(self):
        result = reverse_dict({"a": 1, "b": 1})
        assert result[1] == ["a", "b"]


# ---------------------------------------------------------------------------
# fsz
# ---------------------------------------------------------------------------


class TestFsz:
    @pytest.mark.parametrize(
        "size,expected",
        [
            (0, "0 B"),
            (1, "1 B"),
            (1024, "1.0 KB"),
            (1024 * 1024, "1.0 MB"),
            (1024**3, "1.0 GB"),
        ],
    )
    def test_sizes(self, size: int, expected: str):
        assert fsz(size) == expected

    def test_negative(self):
        assert fsz(-1024) == "1.0 KB"


# ---------------------------------------------------------------------------
# safe_delete
# ---------------------------------------------------------------------------


class TestSafeDelete:
    def test_delete_file(self, text_file: Path):
        assert safe_delete(text_file) is True
        assert not text_file.exists()

    def test_delete_dir(self, sample_tree: Path):
        assert safe_delete(sample_tree) is True
        assert not sample_tree.exists()

    def test_missing_returns_false(self, tmp_path: Path):
        assert safe_delete(tmp_path / "nope") is False


# ---------------------------------------------------------------------------
# unique_path / _clean_fname
# ---------------------------------------------------------------------------


class TestUniquePath:
    def test_nonexistent_returns_same(self, tmp_path: Path):
        p = tmp_path / "new.txt"
        assert unique_path(p) == p

    def test_existing_appends_counter(self, tmp_path: Path):
        p = tmp_path / "a.txt"
        p.write_text("x")
        result = unique_path(p)
        assert result.name == "a_1.txt"

    def test_clean_removes_counter(self, tmp_path: Path):
        p = tmp_path / "a_3.txt"
        assert _clean_fname(p).name == "a.txt"


# ---------------------------------------------------------------------------
# runcmd
# ---------------------------------------------------------------------------


class TestRuncmd:
    def test_empty_raises(self):
        with pytest.raises(ValueError):
            runcmd([])

    def test_success(self):
        rc, out, err = runcmd(["python", "-c", "print('hi')"], show_output=False)
        assert rc == 0
        assert "hi" in out

    def test_not_found(self):
        rc, out, err = runcmd(["definitely-not-a-command-xyz"], show_output=False)
        assert rc == 127

    def test_timeout(self):
        rc, out, err = runcmd(
            ["python", "-c", "import time; time.sleep(5)"],
            timeout=0.2,
            show_output=False,
        )
        assert rc == 124

    def test_silent(self):
        rc, out, err = runcmd(["python", "-c", "print('hi')"], run_silently=True)
        assert rc == 0
        assert out == "" and err == ""


# ---------------------------------------------------------------------------
# write_txt_file / append_text
# ---------------------------------------------------------------------------


class TestWriteAppend:
    def test_write_new(self, tmp_path: Path):
        p = tmp_path / "out.txt"
        assert write_txt_file(p, "hello") is True
        assert p.read_text() == "hello"

    def test_write_no_overwrite(self, tmp_path: Path):
        p = tmp_path / "out.txt"
        p.write_text("orig")
        assert write_txt_file(p, "new", overwrite=False) is False
        assert p.read_text() == "orig"

    def test_write_overwrite(self, tmp_path: Path):
        p = tmp_path / "out.txt"
        p.write_text("orig")
        assert write_txt_file(p, "new", overwrite=True) is True
        assert p.read_text() == "new"

    def test_write_non_str(self, tmp_path: Path):
        assert write_txt_file(tmp_path / "x", 123) is False

    def test_append_new(self, tmp_path: Path):
        p = tmp_path / "a.txt"
        assert append_text(p, "first") is True
        assert p.read_text() == "first"

    def test_append_existing(self, tmp_path: Path):
        p = tmp_path / "a.txt"
        p.write_text("first")
        assert append_text(p, "second") is True
        assert p.read_text() == "first\nsecond"

    def test_append_to_dir_fails(self, tmp_path: Path):
        assert append_text(tmp_path, "x") is False


# ---------------------------------------------------------------------------
# should_skip
# ---------------------------------------------------------------------------


class TestShouldSkip:
    def test_skip_pycache_part(self, tmp_path: Path):
        p = tmp_path / "__pycache__" / "x.pyc"
        p.parent.mkdir()
        p.touch()
        assert should_skip(p) is True

    def test_regular_file(self, text_file: Path):
        assert should_skip(text_file) is False


# ---------------------------------------------------------------------------
# get_removed_lines
# ---------------------------------------------------------------------------


class TestGetRemovedLines:
    def test_basic(self):
        assert get_removed_lines("a\nb\nc", "a\nc") == ["b"]

    def test_ignores_blank(self):
        assert get_removed_lines("a\n\nb", "a\nb") == []


# ---------------------------------------------------------------------------
# restore_bak
# ---------------------------------------------------------------------------


class TestRestoreBak:
    def test_restore(self, tmp_path: Path):
        p = tmp_path / "file.txt"
        bak = tmp_path / "file.txt.bak"
        bak.write_text("old")
        assert restore_bak(p) is True
        assert p.read_text() == "old"
        assert not bak.exists()

    def test_no_bak(self, tmp_path: Path):
        assert restore_bak(tmp_path / "missing.txt") is False


# ---------------------------------------------------------------------------
# rrs (smoke test)
# ---------------------------------------------------------------------------


class TestRrs:
    def test_rrs_prints(self, capsys):
        rrs(Path("x.bin"), 1000, 500)
        out = capsys.readouterr().out
        assert "x.bin" in out

    def test_rrs_no_change(self, capsys):
        rrs(Path("x.bin"), 100, 100)
        out = capsys.readouterr().out
        assert "NO CHANGE" in out


# ---------------------------------------------------------------------------
# is_empty
# ---------------------------------------------------------------------------


class TestIsEmpty:
    def test_empty(self, tmp_path: Path):
        d = tmp_path / "empty"
        d.mkdir()
        assert is_empty(d) is True

    def test_non_empty(self, tmp_path: Path):
        d = tmp_path / "full"
        d.mkdir()
        (d / "x").touch()
        assert is_empty(d) is False

    def test_file_returns_false(self, text_file: Path):
        assert is_empty(text_file) is False


# ---------------------------------------------------------------------------
# File-gathering functions
# ---------------------------------------------------------------------------


class TestFileGatherers:
    def test_get_files_scandir(self, sample_tree: Path):
        files = get_files_scandir(sample_tree)
        names = {f.name for f in files}
        assert {"a.txt", "b.py", "c.txt", "d.bin"} <= names

    def test_get_files_scandir_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            get_files_scandir(tmp_path / "nope")

    def test_get_files_scandir_not_dir(self, text_file: Path):
        with pytest.raises(NotADirectoryError):
            get_files_scandir(text_file)

    def test_get_files_scandir_ext_filter(self, sample_tree: Path):
        files = get_files_scandir(sample_tree, ext=[".txt"])
        assert all(f.suffix == ".txt" for f in files)

    def test_get_files4(self, sample_tree: Path):
        files = get_files4(sample_tree)
        assert any(f.name == "a.txt" for f in files)

    def test_get_files_pathlib(self, sample_tree: Path):
        files = get_files_pathlib(sample_tree)
        assert any(f.name == "a.txt" for f in files)

    def test_get_files_iter(self, sample_tree: Path):
        files = list(get_files_iter(sample_tree))
        assert any(f.name == "a.txt" for f in files)

    def test_get_files_iter_not_dir(self, text_file: Path):
        with pytest.raises(NotADirectoryError):
            list(get_files_iter(text_file))

    def test_get_files(self, sample_tree: Path):
        files = get_files(sample_tree)
        assert any(f.name == "a.txt" for f in files)

    def test_get_files_ext_filter(self, sample_tree: Path):
        files = get_files(sample_tree, ext=[".py"])
        assert all(f.suffix == ".py" for f in files)

    def test_getfiles(self, sample_tree: Path):
        files = getfiles(sample_tree)
        assert len(files) > 0

    def test_get_fast(self, sample_tree: Path):
        files = list(get_fast(sample_tree))
        assert any(f.name == "a.txt" for f in files)


# ---------------------------------------------------------------------------
# is_python_file / get_pyfiles
# ---------------------------------------------------------------------------


class TestPythonFiles:
    def test_simple_py(self, tmp_path: Path):
        p = tmp_path / "x.py"
        p.write_text("x = 1")
        assert is_python_file(p) is True

    def test_non_py_suffix(self, tmp_path: Path):
        p = tmp_path / "x.txt"
        p.write_text("x = 1")
        assert is_python_file(p) is False

    def test_empty_file(self, tmp_path: Path):
        p = tmp_path / "e.py"
        p.write_text("")
        assert is_python_file(p) is False

    def test_extensionless_python(self, tmp_path: Path):
        p = tmp_path / "script"
        p.write_text("x = 1\n")
        assert is_python_file(p) is True

    def test_shebang_python(self, tmp_path: Path):
        p = tmp_path / "runme"
        p.write_bytes(b"#!/usr/bin/env python\nx=1\n")
        assert is_python_file(p) is True

    def test_binary_rejected(self, binary_file: Path):
        assert is_python_file(binary_file) is False

    def test_get_pyfiles_dir(self, sample_tree: Path):
        files = get_pyfiles(sample_tree)
        names = {f.name for f in files}
        assert "b.py" in names

    def test_get_pyfiles_single(self, tmp_path: Path):
        p = tmp_path / "x.py"
        p.write_text("x")
        assert get_pyfiles(p) == [p]

    def test_get_pyfiles_iter(self, sample_tree: Path):
        files = list(get_pyfiles_iter(sample_tree))
        assert any(f.name == "b.py" for f in files)

    def test_get_pyfiles_iter_skips_pycache(self, sample_tree: Path):
        files = list(get_pyfiles_iter(sample_tree))
        assert not any("__pycache__" in f.parts for f in files)


# ---------------------------------------------------------------------------
# gsz / _dir_size
# ---------------------------------------------------------------------------


class TestGsz:
    def test_file_size(self, text_file: Path):
        assert gsz(text_file) == text_file.stat().st_size

    def test_dir_size(self, sample_tree: Path):
        total = gsz(sample_tree)
        assert total > 0

    def test_missing(self, tmp_path: Path):
        assert gsz(tmp_path / "nope") == 0

    def test_symlink_returns_zero(self, tmp_path: Path):
        target = tmp_path / "real.txt"
        target.write_text("x")
        link = tmp_path / "link.txt"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlinks not supported")
        assert gsz(link) == 0


# ---------------------------------------------------------------------------
# walk_paths / walk_files / walkfiles
# ---------------------------------------------------------------------------


class TestWalkers:
    def test_walk_paths_single_file(self, text_file: Path):
        result = list(walk_paths(text_file))
        assert result == [text_file]

    def test_walk_paths_dir(self, sample_tree: Path):
        result = list(walk_paths(sample_tree))
        assert any(p.name == "a.txt" for p in result)

    def test_walk_paths_ext_filter(self, sample_tree: Path):
        result = list(walk_paths(sample_tree, ext=[".txt"]))
        assert all(p.suffix == ".txt" for p in result)

    def test_walk_files(self, sample_tree: Path):
        files = walk_files(sample_tree)
        assert any(f.name == "a.txt" for f in files)

    def test_walk_files_ext(self, sample_tree: Path):
        files = walk_files(sample_tree, ext=[".py"])
        assert all(f.suffix == ".py" for f in files)

    def test_walkfiles(self, sample_tree: Path):
        files = list(walkfiles(sample_tree))
        assert any(f.name == "a.txt" for f in files)


# ---------------------------------------------------------------------------
# is_text_file / _check_binary_chunk
# ---------------------------------------------------------------------------


class TestTextDetection:
    def test_text_file(self, text_file: Path):
        assert is_text_file(text_file) is True

    def test_binary_file(self, binary_file: Path):
        assert is_text_file(binary_file) is False

    def test_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            is_text_file(tmp_path / "nope")

    def test_dir_raises(self, tmp_path: Path):
        with pytest.raises(ValueError):
            is_text_file(tmp_path)

    def test_check_binary_empty(self):
        assert _check_binary_chunk(b"") is False

    def test_check_binary_null(self):
        assert _check_binary_chunk(b"\x00" * 100) is True

    def test_check_binary_text(self):
        assert _check_binary_chunk(b"hello world\n" * 20) is False


# ---------------------------------------------------------------------------
# atomic_write
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_writes_content(self, tmp_path: Path):
        p = tmp_path / "out.txt"
        atomic_write(p, "hello")
        assert p.read_text() == "hello"

    def test_overwrites(self, tmp_path: Path):
        p = tmp_path / "out.txt"
        p.write_text("old")
        atomic_write(p, "new")
        assert p.read_text() == "new"


# ---------------------------------------------------------------------------
# remove_blank_lines
# ---------------------------------------------------------------------------


class TestRemoveBlankLines:
    def test_collapses_consecutive(self):
        assert remove_blank_lines("a\n\n\nb") == "a\n\nb"

    def test_preserves_single(self):
        assert remove_blank_lines("a\n\nb") == "a\n\nb"

    def test_no_blanks(self):
        assert remove_blank_lines("a\nb") == "a\nb"


# ---------------------------------------------------------------------------
# get_files_iter_config
# ---------------------------------------------------------------------------


class TestGetFilesIterConfig:
    def test_walks_directory(self, sample_tree: Path):
        config = FileWalkerConfig()
        files = list(get_files_iter_config(sample_tree, config))
        assert any(f.name == "a.txt" for f in files)

    def test_skip_hidden(self, sample_tree: Path):
        hidden = sample_tree / ".hidden"
        hidden.write_text("x")
        config = FileWalkerConfig(skip_hidden=True)
        files = list(get_files_iter_config(sample_tree, config))
        assert not any(f.name == ".hidden" for f in files)

    def test_file_pattern(self, sample_tree: Path):
        config = FileWalkerConfig(file_pattern="*.txt", exclude_pattern=None)
        files = list(get_files_iter_config(sample_tree, config))
        assert all(f.suffix == ".txt" for f in files)

    def test_nonexistent_path(self, tmp_path: Path, capsys):
        result = list(get_files_iter_config(tmp_path / "nope"))
        assert result == []
        out = capsys.readouterr().out
        assert "Warning" in out

    def test_single_file(self, text_file: Path):
        files = list(get_files_iter_config(text_file))
        assert files == [text_file]


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------


class TestReportGenerator:
    def test_add_item_and_stats(self):
        rg = ReportGenerator("Test")
        rg.add_item(ReportItem(path="a", category="success"))
        rg.add_item(ReportItem(path="b", category="success"))
        rg.add_item(ReportItem(path="c", category="error"))
        assert rg.stats["success"] == 2
        assert rg.stats["error"] == 1

    def test_print_report(self, capsys):
        rg = ReportGenerator("My Report")
        rg.add_item(ReportItem(path="a", category="success"))
        rg.print_report()
        out = capsys.readouterr().out
        assert "My Report" in out

    def test_export_text(self, tmp_path: Path):
        rg = ReportGenerator("Rep")
        rg.add_item(ReportItem(path="a", category="success"))
        out = tmp_path / "report.txt"
        rg.export_to_file(out, format="text")
        assert "a" in out.read_text()

    def test_export_csv(self, tmp_path: Path):
        rg = ReportGenerator("Rep")
        rg.add_item(ReportItem(path="a", category="success"))
        out = tmp_path / "report.csv"
        rg.export_to_file(out, format="csv")
        content = out.read_text()
        assert "Path,Category" in content

    def test_add_stat(self):
        rg = ReportGenerator()
        rg.add_stat("total", 5)
        assert rg.stats["total"] == 5


# ---------------------------------------------------------------------------
# copy_dir / move_dir
# ---------------------------------------------------------------------------


class TestCopyMoveDir:
    def test_copy_dir(self, tmp_path: Path):
        from fileutils import copy_dir

        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("hello")
        dst = tmp_path / "dst"
        dst.mkdir()
        assert copy_dir(str(src), str(dst)) is True
        assert (dst / "src" / "a.txt").read_text() == "hello"

    def test_copy_dir_missing(self, tmp_path: Path):
        from fileutils import copy_dir

        with mock.patch("builtins.print"):
            assert copy_dir(str(tmp_path / "nope"), str(tmp_path)) is False

    def test_move_dir(self, tmp_path: Path):
        from fileutils import move_dir

        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("hello")
        dst = tmp_path / "dst"
        dst.mkdir()
        assert move_dir(str(src), str(dst)) is True
        assert (dst / "src" / "a.txt").read_text() == "hello"

    def test_move_dir_missing(self, tmp_path: Path):
        from fileutils import move_dir

        with mock.patch("builtins.print"):
            assert move_dir(str(tmp_path / "nope"), str(tmp_path)) is False


# ---------------------------------------------------------------------------
# get_nobinary
# ---------------------------------------------------------------------------


class TestGetNobinary:
    def test_filters_binaries(self, sample_tree: Path):
        files = get_nobinary(sample_tree)
        assert all(not f.name.endswith(".bin") for f in files)


# ---------------------------------------------------------------------------
# Constants exist
# ---------------------------------------------------------------------------


class TestConstants:
    def test_color_codes(self):
        for c in (BOLD, GREEN, YELLOW, CYAN, RED, RESET, DIM):
            assert isinstance(c, str)
