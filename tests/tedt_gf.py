from pathlib import Path

import pytest


def get_files(directory: Path, extensions: list[str] | None = None) -> list[Path]:
    found_files = []
    if extensions is None or not extensions:
        for item in directory.rglob("*"):
            if item.is_file() and not item.is_symlink():
                found_files.append(item)
        return found_files
    for ext in extensions:
        if ext == "":
            for item in directory.rglob("*"):
                if item.is_file() and item.suffix == "" and not item.is_symlink():
                    if item not in found_files:
                        found_files.append(item)
        else:
            if not ext.startswith("."):
                ext = "." + ext
            for item in directory.rglob(f"*{ext}"):
                if item.is_file() and not item.is_symlink():
                    if item not in found_files:
                        found_files.append(item)
    return found_files


@pytest.fixture
def setup_test_directory(tmp_path: Path) -> dict[str, Path | list[Path]]:
    base_dir = tmp_path / "test_root"
    base_dir.mkdir()
    (base_dir / "file1.txt").write_text("content1")
    (base_dir / "file2.log").write_text("content2")
    (base_dir / "document").write_text("no extension content")
    (base_dir / "config_file").write_text("config content")
    (base_dir / "script.py").write_text("print('hello')")
    (base_dir / "data.json").write_text("{}")
    subdir1 = base_dir / "subdir1"
    subdir1.mkdir()
    (subdir1 / "subfile1.txt").write_text("subcontent1")
    (subdir1 / "archive.zip").write_text("zip content")
    (subdir1 / "readme").write_text("readme content")
    subdir2 = base_dir / "subdir2"
    subdir2.mkdir()
    (subdir2 / "main.py").write_text("import sys")
    (subdir2 / "notes").write_text("notes content")
    (subdir2 / "temp.log").write_text("temp log content")
    symlink_dir = base_dir / "symlink_only_dir"
    symlink_dir.mkdir()
    target_file_txt = base_dir / "target_for_symlink.txt"
    target_file_txt.write_text("symlink target")
    target_file_no_ext = base_dir / "target_no_ext"
    target_file_no_ext.write_text("symlink target no ext")
    try:
        (symlink_dir / "link_to_txt.txt").symlink_to(target_file_txt)
        (symlink_dir / "link_no_ext").symlink_to(target_file_no_ext)
        (symlink_dir / "link_to_subdir").symlink_to(subdir1)
        (base_dir / "symlinked_file.log").symlink_to(base_dir / "file2.log")
        (base_dir / "symlinked_no_ext").symlink_to(base_dir / "document")
    except OSError as e:
        pytest.skip(f"Could not create symlinks: {e}. Skipping symlink tests.")
    empty_subdir = base_dir / "empty_subdir"
    empty_subdir.mkdir()
    expected_files_default = sorted(
        [
            base_dir / "file1.txt",
            base_dir / "file2.log",
            base_dir / "document",
            base_dir / "config_file",
            base_dir / "script.py",
            base_dir / "data.json",
            subdir1 / "subfile1.txt",
            subdir1 / "archive.zip",
            subdir1 / "readme",
            subdir2 / "main.py",
            subdir2 / "notes",
            subdir2 / "temp.log",
        ]
    )
    expected_files_no_ext = sorted(
        [
            base_dir / "document",
            base_dir / "config_file",
            subdir1 / "readme",
            subdir2 / "notes",
        ]
    )
    expected_files_txt = sorted(
        [
            base_dir / "file1.txt",
            subdir1 / "subfile1.txt",
        ]
    )
    expected_files_py = sorted(
        [
            base_dir / "script.py",
            subdir2 / "main.py",
        ]
    )
    expected_files_log = sorted(
        [
            base_dir / "file2.log",
            subdir2 / "temp.log",
        ]
    )
    return {
        "base_dir": base_dir,
        "expected_files_default": expected_files_default,
        "expected_files_no_ext": expected_files_no_ext,
        "expected_files_txt": expected_files_txt,
        "expected_files_py": expected_files_py,
        "expected_files_log": expected_files_log,
    }


def test_get_files_default(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    expected = data["expected_files_default"]
    result = get_files(base_dir)
    assert sorted(result) == sorted(expected)
    assert all(f.is_file() and not f.is_symlink() for f in result)


def test_get_files_no_extensions_explicit(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    expected = data["expected_files_default"]
    result = get_files(base_dir, extensions=[])
    assert sorted(result) == sorted(expected)
    assert all(f.is_file() and not f.is_symlink() for f in result)


def test_get_files_none_extensions(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    expected = data["expected_files_default"]
    result = get_files(base_dir, extensions=None)
    assert sorted(result) == sorted(expected)
    assert all(f.is_file() and not f.is_symlink() for f in result)


def test_get_files_no_extension_files_only(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    expected = data["expected_files_no_ext"]
    result = get_files(base_dir, extensions=[""])
    assert sorted(result) == sorted(expected)
    assert all(f.is_file() and not f.is_symlink() and f.suffix == "" for f in result)


def test_get_files_specific_extensions(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    expected = sorted(data["expected_files_txt"] + data["expected_files_py"])
    result = get_files(base_dir, extensions=[".txt", ".py"])
    assert sorted(result) == sorted(expected)
    assert all(f.is_file() and not f.is_symlink() for f in result)
    assert all(f.suffix in [".txt", ".py"] for f in result)


def test_get_files_specific_extensions_no_dot(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    expected = data["expected_files_log"]
    result = get_files(base_dir, extensions=["log"])
    assert sorted(result) == sorted(expected)
    assert all(f.is_file() and not f.is_symlink() for f in result)
    assert all(f.suffix == ".log" for f in result)


def test_get_files_mixed_extensions_and_no_ext(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    expected = sorted(data["expected_files_log"] + data["expected_files_no_ext"])
    result = get_files(base_dir, extensions=[".log", ""])
    assert sorted(result) == sorted(expected)
    assert all(f.is_file() and not f.is_symlink() for f in result)
    assert all(f.suffix in [".log", ""] for f in result)


def test_get_files_non_existent_directory(tmp_path: Path) -> None:
    non_existent_dir = tmp_path / "i_do_not_exist"
    assert not non_existent_dir.exists()
    result = get_files(non_existent_dir)
    assert result == []
    result_with_ext = get_files(non_existent_dir, extensions=[".txt"])
    assert result_with_ext == []


def test_get_files_empty_directory(setup_test_directory) -> None:
    data = setup_test_directory
    empty_subdir = data["base_dir"] / "empty_subdir"
    assert not any(empty_subdir.iterdir())
    result_default = get_files(empty_subdir)
    assert result_default == []
    result_ext = get_files(empty_subdir, extensions=[".txt"])
    assert result_ext == []
    result_no_ext = get_files(empty_subdir, extensions=[""])
    assert result_no_ext == []


def test_get_files_symlinks_only_ignored(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    symlink_to_txt = base_dir / "symlinked_file.log"
    assert symlink_to_txt.is_symlink()
    assert not symlink_to_txt.is_file()
    result_logs = get_files(base_dir, extensions=[".log"])
    assert symlink_to_txt not in result_logs
    assert base_dir / "file2.log" in result_logs
    symlink_to_no_ext = base_dir / "symlinked_no_ext"
    assert symlink_to_no_ext.is_symlink()
    assert not symlink_to_no_ext.is_file()
    result_no_ext = get_files(base_dir, extensions=[""])
    assert symlink_to_no_ext not in result_no_ext
    assert base_dir / "document" in result_no_ext
    result_default = get_files(base_dir)
    assert symlink_to_txt not in result_default
    assert symlink_to_no_ext not in result_default
    expected_regular_files = data["expected_files_default"]
    assert sorted(result_default) == sorted(expected_regular_files)


def test_get_files_recursive_search(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    subdir1_files = [
        base_dir / "subdir1" / f for f in ["subfile1.txt", "archive.zip", "readme"]
    ]
    subdir2_files = [base_dir / "subdir2" / f for f in ["main.py", "notes", "temp.log"]]
    result_default = get_files(base_dir)
    for f in subdir1_files + subdir2_files:
        assert f in result_default
    result_txt = get_files(base_dir, extensions=[".txt"])
    assert base_dir / "subdir1" / "subfile1.txt" in result_txt
    assert base_dir / "file1.txt" in result_txt
    result_no_ext = get_files(base_dir, extensions=[""])
    assert base_dir / "subdir1" / "readme" in result_no_ext
    assert base_dir / "subdir2" / "notes" in result_no_ext
    assert base_dir / "document" in result_no_ext


def test_get_files_with_pathlib_path_object(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir_path = Path(data["base_dir"])
    expected = data["expected_files_default"]
    result = get_files(base_dir_path)
    assert sorted(result) == sorted(expected)


def test_get_files_with_dot_in_filename_no_extension(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    (base_dir / ".profile").write_text("profile content")
    (base_dir / "archive.tar").write_text("tar content")
    (base_dir / "folder.name").mkdir()
    (base_dir / "folder.name" / "file_in_dotted_folder").write_text("content")
    expected_no_ext = sorted(data["expected_files_no_ext"] + [base_dir / ".profile"])
    expected_default = sorted(
        data["expected_files_default"]
        + [
            base_dir / ".profile",
            base_dir / "archive.tar",
            base_dir / "folder.name" / "file_in_dotted_folder",
        ]
    )
    result_no_ext = get_files(base_dir, extensions=[""])
    assert sorted(result_no_ext) == sorted(expected_no_ext)
    assert all(
        f.is_file() and not f.is_symlink() and f.suffix == "" for f in result_no_ext
    )
    result_default = get_files(base_dir)
    assert sorted(result_default) == sorted(expected_default)
    assert all(f.is_file() and not f.is_symlink() for f in result_default)
