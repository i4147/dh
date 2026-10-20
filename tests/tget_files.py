from dh import get_files
import pytest


@pytest.fixture
def setup_test_directory(tmp_path: Path):
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
    target_file_txt = base_dir / "target_regular_file.txt"
    target_file_txt.write_text("symlink target txt")
    target_file_no_ext = base_dir / "target_regular_no_ext"
    target_file_no_ext.write_text("symlink target no ext")
    target_file_log = base_dir / "target_regular_file.log"
    target_file_log.write_text("symlink target log")
    symlink_dir = base_dir / "symlink_dir"
    symlink_dir.mkdir()
    symlinks_to_create = {
        symlink_dir / "link_to_txt.txt": target_file_txt,
        symlink_dir / "link_to_no_ext": target_file_no_ext,
        symlink_dir / "link_to_log.log": target_file_log,
        base_dir / "symlinked_file.log": base_dir / "file2.log",
        base_dir / "symlinked_no_ext": base_dir / "document",
        base_dir / "symlinked_dir_link": subdir1,
    }
    created_symlinks = []
    try:
        for link_path, target_path in symlinks_to_create.items():
            if not target_path.exists():
                target_path.write_text(f"dummy target for {target_path.name}")
            link_path.symlink_to(target_path)
            created_symlinks.append(link_path)
    except OSError as e:
        pytest.skip(f"Could not create symlinks: {e}. Skipping symlink tests.")
    expected_files_default = sorted([
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
    ])
    expected_files_no_ext = sorted([
        base_dir / "document",
        base_dir / "config_file",
        subdir1 / "readme",
        subdir2 / "notes",
    ])
    expected_files_txt = sorted([
        base_dir / "file1.txt",
        subdir1 / "subfile1.txt",
    ])
    expected_files_py = sorted([
        base_dir / "script.py",
        subdir2 / "main.py",
    ])
    expected_files_log = sorted([
        base_dir / "file2.log",
        subdir2 / "temp.log",
    ])
    return {
        "base_dir": base_dir,
        "expected_files_default": expected_files_default,
        "expected_files_no_ext": expected_files_no_ext,
        "expected_files_txt": expected_files_txt,
        "expected_files_py": expected_files_py,
        "expected_files_log": expected_files_log,
        "created_symlinks": created_symlinks,
        "target_file_txt": target_file_txt,
        "target_file_no_ext": target_file_no_ext,
        "target_file_log": target_file_log,
    }


def test_get_files_symlinks_only_ignored(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    symlink_in_root_log = base_dir / "symlinked_file.log"
    assert symlink_in_root_log.is_symlink()
    assert not symlink_in_root_log.is_file()
    result_logs = get_files(base_dir, extensions=[".log"])
    assert symlink_in_root_log not in result_logs, "Symlink to .log file should not be returned when searching for .log"
    assert base_dir / "file2.log" in result_logs, "Regular .log file was not returned"
    symlink_in_root_no_ext = base_dir / "symlinked_no_ext"
    assert symlink_in_root_no_ext.is_symlink()
    assert not symlink_in_root_no_ext.is_file()
    result_no_ext = get_files(base_dir, extensions=[""])
    assert symlink_in_root_no_ext not in result_no_ext, (
        "Symlink to no-ext file should not be returned when searching for no-ext"
    )
    assert base_dir / "document" in result_no_ext, "Regular no-ext file was not returned"
    result_default = get_files(base_dir)
    for symlink_path in data["created_symlinks"]:
        assert symlink_path not in result_default, f"Symlink '{symlink_path.name}' was found in default results."
    expected_regular_files = data["expected_files_default"]
    assert sorted(result_default) == sorted(expected_regular_files), (
        "Default call did not return the correct set of regular files."
    )
    symlink_to_dir = base_dir / "symlinked_dir_link"
    assert symlink_to_dir.is_symlink()
    assert not symlink_to_dir.is_file()
    result_txt_after_dir_symlink = get_files(base_dir, extensions=[".txt"])
    assert symlink_to_dir not in result_txt_after_dir_symlink
    assert base_dir / "subdir1" / "subfile1.txt" in result_txt_after_dir_symlink


def test_get_files_specific_extensions(setup_test_directory) -> None:
    data = setup_test_directory
    base_dir = data["base_dir"]
    expected = sorted(data["expected_files_txt"] + data["expected_files_py"])
    result = get_files(base_dir, extensions=[".txt", ".py"])
    assert all(f.is_file() and not f.is_symlink() for f in result)
    assert sorted(result) == sorted(expected)
    for symlink_path in data["created_symlinks"]:
        assert symlink_path not in result, f"Symlink '{symlink_path.name}' found when searching for .txt/.py"
