"""Regression coverage for the consolidated traversal API."""

from pathlib import Path

import pytest
import dh
from dh import fileutils


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    for name, data in {
        "guide.rst": b"hello",
        "other.txt": b"text",
        "upper.RST": b"case",
        "source.py": b"",
        "script": b"#!/usr/bin/env python3\nprint(1)",
        "plain": b"no shebang",
        "data.bin": b"\x00\x01",
        "nested/child.rst": b"nested",
        "skip/ignored.rst": b"skip",
        ".git/hidden.rst": b"hidden",
        "__pycache__/cache.rst": b"cache",
    }.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return tmp_path


@pytest.mark.parametrize("ext", [[".rst"], ["rst"], ["RST"]])
def test_extension_filter(tree: Path, ext: list[str]) -> None:
    files = fileutils.get_files(tree, ext=ext, skip_dirs={"skip", "__pycache__"})
    assert {p.relative_to(tree).as_posix() for p in files} == {"guide.rst", "upper.RST", "nested/child.rst"}
    assert all(isinstance(p, Path) for p in files)
    assert files == sorted(files)


def test_directory_mode(tree: Path) -> None:
    dirs = fileutils.get_files(
        tree, ext=[".absent"], nobinary=True, pyfiles=True, dirs_only=True, skip_dirs={"skip", "__pycache__"}
    )
    assert set(dirs) == {tree, tree / "nested"}
    assert set(fileutils.get_dirs(tree)) == set(fileutils.get_files(tree, dirs_only=True))


def test_combined_filters(tree: Path) -> None:
    assert fileutils.get_files(tree, ext=[".py"], pyfiles=True) == [tree / "source.py"]
    assert set(fileutils.get_pyfiles(tree)) == {tree / "source.py", tree / "script"}
    assert tree / "data.bin" not in fileutils.get_nobinary(tree)
    assert fileutils.get_files(tree, ext=[]) == fileutils.get_files(tree)


def test_single_file_and_missing(tree: Path) -> None:
    assert fileutils.get_files(tree / "guide.rst", ["txt"]) == []
    assert fileutils.get_files(tree / "guide.rst") == [tree / "guide.rst"]
    with pytest.raises(OSError):
        fileutils.get_files(tree / "missing")


def test_symlinks_are_not_followed(tree: Path) -> None:
    (tree / "link").symlink_to(tree / "nested", target_is_directory=True)
    (tree / "filelink.rst").symlink_to(tree / "guide.rst")
    assert tree / "filelink.rst" not in fileutils.get_files(tree)
    assert fileutils.get_files(tree / "link") == []


def test_scandir_prunes_before_descent(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    real_scandir = os.scandir
    opened = []

    def tracked(path: Path):
        opened.append(Path(path))
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", tracked)
    fileutils.get_files(tree, skip_dirs={"skip", "__pycache__"})
    assert tree / "skip" not in opened
    assert tree / "__pycache__" not in opened
    assert tree / "nested" in opened


def test_walker_errors_propagate(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    def denied(path: Path):
        raise PermissionError(path)

    monkeypatch.setattr(os, "scandir", denied)
    with pytest.raises(PermissionError):
        fileutils.get_files(tree)


def test_custom_skips_replace_defaults(tree: Path) -> None:
    assert tree / "__pycache__" / "cache.rst" in fileutils.get_files(tree, skip_dirs=set())
    assert tree / "__pycache__" / "cache.rst" not in fileutils.get_files(tree)


def test_legacy_walkers_share_scandir(tree: Path) -> None:
    assert tree / "guide.rst" in fileutils.get_files_scandir(tree, ext=[".rst"])
    assert tree / "nested" / "child.rst" in list(fileutils.walker(tree, exts=["rst"]))
    assert tree / "nested" / "child.rst" not in list(fileutils.walker(tree, recursive=False))


def test_file_iterator_does_not_collect_whole_tree(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    real_scandir = os.scandir
    opened = []

    def tracked(path: Path):
        opened.append(Path(path))
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", tracked)
    files = fileutils.get_filez(tree)
    assert opened == []
    next(files)
    assert opened == [tree]
    files.close()
