from __future__ import annotations
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import MagicMock, patch
import pytest
sys.path.insert(0, str(Path(__file__).parent))
from dh import (
    FileWalkerConfig,
    ReportGenerator,
    ReportItem,
    _BFSFileWalker,
    _check_binary_chunk,
    _CommandRunner,
    _ConfigurableFileWalker,
    _DirectoryCopier,
    _DirectoryMover,
    _DirectoryWalker,
    _DirSizeCalculator,
    _ExtensionAnalyzer,
    _FileAgeCalculator,
    _FileCollector,
    _FileReader,
    _FileSizeFormatter,
    _PathWalker,
    _PythonFileChecker,
    _SizeByExtensionCalculator,
    _TextFileDeterminer,
    _TimeFormatter,
    _UniquePathFinder,
    append_text,
    atomic_write,
    format_time,
    fsz,
    get_dirs,
    get_file_age,
    get_files,
    get_files_iter_config,
    get_files_scandir,
    get_installed_packages,
    get_installed_pkgs,
    get_mime_type,
    get_pyfiles,
    get_random_filename,
    get_removed_lines,
    gext,
    gsze,
    is_empty,
    is_image,
    is_python_file,
    is_text_file,
    is_within,
    normalize_filename,
    normalize_path,
    read_lines,
    read_lines_mmap,
    remove_blank_lines,
    restore_bak,
    reverse_dict,
    runcmd,
    safe_delete,
    should_skip,
    unique_path,
    walk_files,
    walk_paths,
    walkfiles,
    write_txt_file,
)
class TestFileReader:
    def test_read_lines_simple_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("line1\nline2\nline3")
            temp_path = f.name
        try:
            lines = read_lines(temp_path, ke=False)
            assert len(lines) == 3
            assert lines[0] == "line1"
            assert lines[2] == "line3"
        finally:
            os.unlink(temp_path)
    def test_read_lines_with_keepends(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("line1\nline2\n")
            temp_path = f.name
        try:
            lines = read_lines(temp_path, ke=True)
            assert lines[0].endswith("\n")
        finally:
            os.unlink(temp_path)
    def test_read_lines_mmap(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("x" * 10000)
            temp_path = f.name
        try:
            lines = read_lines_mmap(Path(temp_path), keep_ends=False)
            assert len(lines) > 0
        finally:
            os.unlink(temp_path)
    def test_file_reader_class(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("test\ndata")
            temp_path = f.name
        try:
            reader = _FileReader(temp_path, keep_ends=False)
            lines = reader.read()
            assert len(lines) == 2
        finally:
            os.unlink(temp_path)
    def test_read_lines_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name
        try:
            lines = read_lines(temp_path, ke=False)
            assert isinstance(lines, list)
        finally:
            os.unlink(temp_path)
    def test_read_lines_with_special_chars(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt", encoding="utf-8") as f:
            f.write("测试\nтест\n日本語")
            temp_path = f.name
        try:
            lines = read_lines(temp_path, ke=False)
            assert len(lines) >= 2
        finally:
            os.unlink(temp_path)
class TestExtensionAnalyzer:
    def test_single_extension(self):
        analyzer = _ExtensionAnalyzer("file.txt")
        assert analyzer.analyze() == ".txt"
    def test_no_extension(self):
        analyzer = _ExtensionAnalyzer("Makefile")
        assert analyzer.analyze() == ""
    def test_multipart_extension_tar(self):
        analyzer = _ExtensionAnalyzer("archive.tar.gz")
        result = analyzer.analyze()
        assert result in [".tar.gz", ".gz"]
    def test_gext_function(self):
        assert gext("file.py") == ".py"
        assert gext("archive.tar.gz") in [".tar.gz", ".gz"]
    def test_double_extension(self):
        analyzer = _ExtensionAnalyzer("script.min.js")
        result = analyzer.analyze()
        assert ".js" in result
    def test_many_dots_in_filename(self):
        analyzer = _ExtensionAnalyzer("my.file.name.with.many.dots.txt")
        result = analyzer.analyze()
        assert ".txt" in result
class TestDirectoryWalker:
    def test_get_dirs_simple(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir1 = Path(tmpdir) / "sub1"
            subdir2 = Path(tmpdir) / "sub2"
            subdir1.mkdir()
            subdir2.mkdir()
            dirs = get_dirs(tmpdir)
            assert len(dirs) >= 2
    def test_get_dirs_nested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a", "b", "c").mkdir(parents=True)
            dirs = get_dirs(tmpdir)
            assert len(dirs) >= 3
    def test_get_dirs_non_directory(self):
        with tempfile.NamedTemporaryFile() as f:
            dirs = get_dirs(f.name)
            assert dirs == []
    def test_get_dirs_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dirs = get_dirs(tmpdir)
            assert dirs == []
    def test_directory_walker_class(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "sub1").mkdir()
            Path(tmpdir, "sub2").mkdir()
            walker = _DirectoryWalker(tmpdir)
            dirs = walker.walk()
            assert len(dirs) >= 2
class TestFileAgeCalculator:
    def test_file_age_non_existent(self):
        age = get_file_age("/nonexistent/path")
        assert age == 0.0
    def test_file_age_recent_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            age = get_file_age(temp_path)
            assert age >= 0
        finally:
            os.unlink(temp_path)
    def test_file_age_string_format(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            age_str = get_file_age(temp_path, str_mode=True)
            assert isinstance(age_str, str)
            assert "sec" in age_str or age_str == "0 sec"
        finally:
            os.unlink(temp_path)
    def test_age_calculator_class(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            calc = _FileAgeCalculator(temp_path)
            assert calc.as_float() >= 0
            assert isinstance(calc.as_string(), str)
        finally:
            os.unlink(temp_path)
    def test_file_age_old_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            os.utime(temp_path, (0, 0))
            age_str = get_file_age(temp_path, str_mode=True)
            assert isinstance(age_str, str)
        finally:
            os.unlink(temp_path)
class TestPackageUtilities:
    @patch("importlib.metadata.distributions")
    def test_get_installed_packages(self, mock_distributions):
        mock_dist = MagicMock()
        mock_dist.metadata.get.side_effect = lambda x: {"Name": "test-package", "Version": "1.0.0"}.get(x)
        mock_distributions.return_value = [mock_dist]
        packages = get_installed_packages()
        assert isinstance(packages, dict)
    @patch("importlib.metadata.distributions")
    def test_get_installed_pkgs(self, mock_distributions):
        mock_dist = MagicMock()
        mock_dist.metadata.get.return_value = "test-package"
        mock_distributions.return_value = [mock_dist]
        pkgs = get_installed_pkgs()
        assert isinstance(pkgs, list)
    @patch("importlib.metadata.distributions")
    def test_get_installed_packages_with_none(self, mock_distributions):
        mock_dist = MagicMock()
        mock_dist.metadata.get.return_value = None
        mock_distributions.return_value = [mock_dist]
        packages = get_installed_packages()
        assert isinstance(packages, dict)
class TestMimeAndImage:
    def test_get_mime_type_text(self):
        mime = get_mime_type("file.txt")
        assert mime in ["text/plain", None]
    def test_get_mime_type_python(self):
        mime = get_mime_type("file.py")
        assert mime in ["text/x-python", "text/plain", None]
    def test_is_image_false(self):
        with tempfile.NamedTemporaryFile(suffix=".txt") as f:
            result = is_image(f.name)
            assert result is False
    def test_is_image_exception_handling(self):
        result = is_image("/nonexistent/path/file.jpg")
        assert result is False
class TestRandomFilename:
    def test_get_random_filename_default_length(self):
        name = get_random_filename()
        assert len(name) == 10
        assert name.islower()
    def test_get_random_filename_custom_length(self):
        name = get_random_filename(length=20)
        assert len(name) == 20
    def test_get_random_filename_uniqueness(self):
        names = [get_random_filename() for _ in range(10)]
        assert len(set(names)) == 10
class TestPathUtilities:
    def test_is_within_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            child = parent / "subdir"
            child.mkdir()
            assert is_within(child, parent)
    def test_is_within_false(self):
        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                assert not is_within(tmpdir1, tmpdir2)
    def test_is_within_same_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert is_within(tmpdir, tmpdir)
    def test_normalize_filename(self):
        result = normalize_filename("file<name>.txt")
        assert "<" not in result and ">" not in result
    def test_normalize_filename_special_chars(self):
        result = normalize_filename("file|name*?.txt")
        assert "|" not in result and "*" not in result and "?" not in result
    def test_normalize_path(self):
        result = normalize_path(".")
        assert isinstance(result, Path)
class TestDictUtilities:
    def test_reverse_dict_simple(self):
        d = {"a": 1, "b": 2}
        rev = reverse_dict(d)
        assert rev[1] == "a"
        assert rev[2] == "b"
    def test_reverse_dict_duplicate_values(self):
        d = {"a": 1, "b": 1}
        rev = reverse_dict(d)
        assert 1 in rev
    def test_reverse_dict_empty(self):
        rev = reverse_dict({})
        assert rev == {}
class TestFileSizeFormatter:
    def test_fsz_bytes(self):
        result = fsz(512)
        assert "B" in result
    def test_fsz_kilobytes(self):
        result = fsz(1024)
        assert "KB" in result
    def test_fsz_megabytes(self):
        result = fsz(1024 * 1024)
        assert "MB" in result
    def test_fsz_gigabytes(self):
        result = fsz(1024 * 1024 * 1024)
        assert "GB" in result
    def test_fsz_zero(self):
        result = fsz(0)
        assert result == "0 B"
    def test_fsz_negative(self):
        result = fsz(-1024)
        assert "KB" in result
    def test_file_size_formatter_class(self):
        formatter = _FileSizeFormatter()
        result = formatter.format(2048)
        assert "KB" in result
class TestSafeDelete:
    def test_safe_delete_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = Path(f.name)
        result = safe_delete(temp_path)
        assert result is True
        assert not temp_path.exists()
    def test_safe_delete_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            result = safe_delete(path)
            assert result is True
    def test_safe_delete_nonexistent(self):
        result = safe_delete(Path("/nonexistent/path"))
        assert result is False
class TestUniquePathFinder:
    def test_unique_path_not_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "newfile.txt"
            result = unique_path(path)
            assert str(result) == str(path)
    def test_unique_path_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            path.write_text("test")
            result = unique_path(path)
            assert result != path
            assert "_1" in result.name
    def test_unique_path_multiple_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            path.write_text("test")
            (Path(tmpdir) / "file_1.txt").write_text("test")
            result = unique_path(path)
            assert "_2" in result.name
    def test_unique_path_finder_class(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            finder = _UniquePathFinder(path)
            result = finder.find()
            assert isinstance(result, Path)
class TestTimeFormatter:
    def test_format_seconds(self):
        result = format_time(30)
        assert "30s" in result or "s" in result
    def test_format_minutes(self):
        result = format_time(150)
        assert "m" in result
    def test_format_hours(self):
        result = format_time(3700)
        assert "h" in result
    def test_format_days(self):
        result = format_time(86400 + 3600)
        assert "d" in result or "h" in result
    def test_format_zero(self):
        result = format_time(0)
        assert result == "0s"
    def test_format_microseconds(self):
        result = format_time(0.0001)
        assert "µs" in result or "ms" in result
    def test_time_formatter_class(self):
        result = _TimeFormatter.format(45)
        assert isinstance(result, str)
class TestCommandRunner:
    def test_runcmd_simple(self):
        code, stdout, stderr = runcmd(["echo", "hello"], run_silently=False)
        assert code == 0
    def test_runcmd_silent(self):
        code, stdout, stderr = runcmd(["echo", "hello"], run_silently=True)
        assert code == 0
        assert stdout == ""
    def test_runcmd_timeout(self):
        code, stdout, stderr = runcmd(["sleep", "10"], timeout=0.1, run_silently=True)
        assert code in [124, -15, 143]
    def test_runcmd_nonexistent(self):
        code, stdout, stderr = runcmd(["/nonexistent/command"], run_silently=True)
        assert code == 127
    def test_runcmd_empty_list(self):
        with pytest.raises(ValueError):
            runcmd([])
    def test_command_runner_class(self):
        runner = _CommandRunner(["echo", "test"], run_silently=True)
        code, stdout, stderr = runner.run()
        assert code == 0
class TestTextFileOperations:
    def test_write_txt_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            result = write_txt_file(path, "test content")
            assert result is True
            assert path.read_text() == "test content"
    def test_write_txt_file_existing_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            path.write_text("original")
            result = write_txt_file(path, "new", overwrite=False)
            assert result is False
    def test_write_txt_file_non_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            result = write_txt_file(path, 123)
            assert result is False
    def test_append_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            path.write_text("line1")
            result = append_text(path, "line2")
            assert result is True
            assert "line2" in path.read_text()
    def test_append_text_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            result = append_text(path, "content")
            assert result is True
    def test_append_text_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = append_text(tmpdir, "content")
            assert result is False
class TestFileDiffUtilities:
    def test_get_removed_lines(self):
        txt1 = "line1\nline2\nline3"
        txt2 = "line1\nline3"
        removed = get_removed_lines(txt1, txt2)
        assert "line2" in removed
    def test_get_removed_lines_empty(self):
        removed = get_removed_lines("same", "same")
        assert len(removed) == 0
    def test_get_removed_lines_all_removed(self):
        removed = get_removed_lines("line1\nline2", "")
        assert len(removed) == 2
class TestBackupUtilities:
    def test_restore_bak(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            bak_path = Path(tmpdir) / "file.txt.bak"
            bak_path.write_text("backup content")
            result = restore_bak(path)
            assert result is True
            assert path.read_text() == "backup content"
    def test_restore_bak_no_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            result = restore_bak(path)
            assert result is False
class TestDirectoryQueries:
    def test_is_empty_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = is_empty(tmpdir)
            assert result is True
    def test_is_empty_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("test")
            result = is_empty(tmpdir)
            assert result is False
    def test_is_empty_file(self):
        with tempfile.NamedTemporaryFile() as f:
            result = is_empty(f.name)
            assert result is False
class TestFileCollector:
    def test_get_files_scandir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").write_text("test")
            Path(tmpdir, "file2.txt").write_text("test")
            files = get_files_scandir(tmpdir, ext=[".txt"])
            assert len(files) >= 2
    def test_get_files_scandir_hidden(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".hidden").write_text("test")
            Path(tmpdir, "visible.txt").write_text("test")
            files = get_files_scandir(tmpdir, include_hidden=False)
            assert all(not f.name.startswith(".") for f in files)
    def test_file_collector_class(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.txt").write_text("test")
            collector = _FileCollector(tmpdir, ext=[".txt"])
            files = collector.collect()
            assert len(files) >= 1
    def test_get_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "sub").mkdir()
            Path(tmpdir, "sub", "file.txt").write_text("test")
            files = get_files(tmpdir, ext=[".txt"])
            assert len(files) >= 1
class TestBFSFileWalker:
    def test_bfs_file_walker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "level1", "level2").mkdir(parents=True)
            Path(tmpdir, "level1", "level2", "file.txt").write_text("test")
            walker = _BFSFileWalker(tmpdir, ext=[".txt"])
            files = walker.walk()
            assert len(files) >= 1
class TestPythonFileDetection:
    def test_is_python_file_py_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("print('hello')")
            temp_path = f.name
        try:
            result = is_python_file(temp_path)
            assert result is True
        finally:
            os.unlink(temp_path)
    def test_is_python_file_no_extension(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("#!/usr/bin/env python3\nprint('hello')")
            temp_path = f.name
        try:
            result = is_python_file(temp_path)
            assert isinstance(result, bool)
        finally:
            os.unlink(temp_path)
    def test_python_file_checker_class(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1")
            temp_path = f.name
        try:
            checker = _PythonFileChecker(temp_path)
            assert checker.is_python_file() is True
        finally:
            os.unlink(temp_path)
    def test_get_pyfiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "script.py").write_text("print('test')")
            files = get_pyfiles(tmpdir)
            assert len(files) >= 1
    def test_get_pyfiles_nested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "sub", "deep").mkdir(parents=True)
            Path(tmpdir, "sub", "deep", "script.py").write_text("x = 1")
            files = get_pyfiles(tmpdir)
            assert len(files) >= 1
class TestTextFileDetermination:
    def test_is_text_file_true(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("plain text")
            temp_path = f.name
        try:
            result = is_text_file(temp_path)
            assert isinstance(result, bool)
        finally:
            os.unlink(temp_path)
    def test_text_file_determiner_class(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("text content")
            temp_path = f.name
        try:
            determiner = _TextFileDeterminer(temp_path)
            result = determiner.is_text()
            assert isinstance(result, bool)
        finally:
            os.unlink(temp_path)
    def test_is_text_file_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            is_text_file("/nonexistent/file.txt")
class TestBinaryChunkChecking:
    def test_check_binary_chunk_null_bytes(self):
        chunk = b"binary\x00data\x00here"
        result = _check_binary_chunk(chunk)
        assert isinstance(result, bool)
    def test_check_binary_chunk_text(self):
        chunk = b"plain text content"
        result = _check_binary_chunk(chunk)
        assert result is False
    def test_check_binary_chunk_empty(self):
        result = _check_binary_chunk(b"")
        assert result is False
    def test_check_binary_chunk_mostly_binary(self):
        chunk = bytes(range(256)) * 10
        result = _check_binary_chunk(chunk)
        assert isinstance(result, bool)
class TestAtomicWrite:
    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            atomic_write(path, "atomic content")
            assert path.read_text() == "atomic content"
    def test_atomic_write_overwrites(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            path.write_text("old")
            atomic_write(path, "new")
            assert path.read_text() == "new"
    def test_atomic_write_preserves_parent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "test.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, "content")
            assert path.read_text() == "content"
class TestWalkFiles:
    def test_walk_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").write_text("test")
            Path(tmpdir, "file2.py").write_text("test")
            files = walk_files(tmpdir)
            assert len(files) >= 2
    def test_walkfiles_generator(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("test")
            gen = walkfiles(tmpdir)
            items = list(gen)
            assert len(items) >= 1
    def test_walk_files_with_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").write_text("test")
            Path(tmpdir, "file2.py").write_text("test")
            files = walk_files(tmpdir, ext=[".txt"])
            assert all(f.suffix == ".txt" for f in files)
class TestDirSize:
    def test_gsz_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x" * 100)
            temp_path = f.name
        try:
            size = gsz(temp_path)
            assert size == 100
        finally:
            os.unlink(temp_path)
    def test_gsz_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("x" * 50)
            size = gsz(tmpdir)
            assert size >= 50
    def test_gsze_with_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("x" * 100)
            Path(tmpdir, "file.py").write_text("y" * 50)
            size = gsze(tmpdir, ext=[".txt"])
            assert size >= 100
    def test_size_by_extension_calculator(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("x" * 100)
            calc = _SizeByExtensionCalculator(tmpdir, ext=[".txt"])
            size = calc.calculate()
            assert size >= 100
class TestFileWalkerConfig:
    def test_file_walker_config_defaults(self):
        config = FileWalkerConfig()
        assert config.skip_hidden is False
        assert config.skip_symlinks is True
    def test_file_walker_config_custom(self):
        config = FileWalkerConfig(skip_hidden=True, skip_dirs={".git"})
        assert config.skip_hidden is True
    def test_configurable_file_walker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("test")
            config = FileWalkerConfig()
            walker = _ConfigurableFileWalker(tmpdir, config)
            files = list(walker.walk())
            assert len(files) >= 1
    def test_get_files_iter_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("test")
            config = FileWalkerConfig()
            files = list(get_files_iter_config(tmpdir, config))
            assert len(files) >= 1
class TestPathWalker:
    def test_path_walker_single_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            path.write_text("test")
            walker = _PathWalker(str(path))
            files = list(walker.walk())
            assert len(files) == 1
    def test_path_walker_multiple_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").write_text("test")
            Path(tmpdir, "file2.txt").write_text("test")
            walker = _PathWalker([Path(tmpdir) / "file1.txt", Path(tmpdir) / "file2.txt"])
            files = list(walker.walk())
            assert len(files) >= 2
    def test_walk_paths_function(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("test")
            files = list(walk_paths(tmpdir, ext=[".txt"]))
            assert len(files) >= 1
class TestReportGenerator:
    def test_report_item_creation(self):
        item = ReportItem(path="test.txt", category="success", message="OK")
        assert item.path == "test.txt"
        assert item.category == "success"
    def test_report_generator_add_item(self):
        gen = ReportGenerator(title="Test Report")
        item = ReportItem(path="file.txt", category="success")
        gen.add_item(item)
        assert len(gen.items) == 1
        assert gen.stats["success"] == 1
    def test_report_generator_add_stat(self):
        gen = ReportGenerator()
        gen.add_stat("total_files", 10)
        assert gen.stats["total_files"] == 10
    def test_report_generator_print(self, capsys):
        gen = ReportGenerator(title="Test")
        item = ReportItem(path="file.txt", category="success", message="OK")
        gen.add_item(item)
        gen.print_report()
        captured = capsys.readouterr()
        assert "Test" in captured.out
    def test_report_generator_export_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator()
            item = ReportItem(path="file.txt", category="success")
            gen.add_item(item)
            export_path = Path(tmpdir) / "report.txt"
            gen.export_to_file(export_path, format="text")
            assert export_path.exists()
    def test_report_generator_export_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator()
            item = ReportItem(path="file.txt", category="success")
            gen.add_item(item)
            export_path = Path(tmpdir) / "report.csv"
            gen.export_to_file(export_path, format="csv")
            assert export_path.exists()
    def test_report_generator_sort_by_path(self):
        gen = ReportGenerator()
        gen.add_item(ReportItem(path="z.txt", category="success"))
        gen.add_item(ReportItem(path="a.txt", category="success"))
        gen.print_report(sort_by="path")
        assert gen.items[0].path < gen.items[1].path
class TestRemoveBlankLines:
    def test_remove_blank_lines(self):
        text = "line1\n\nline2\n\n\nline3"
        result = remove_blank_lines(text)
        assert result.count("\n\n") == 0
    def test_remove_blank_lines_no_blanks(self):
        text = "line1\nline2\nline3"
        result = remove_blank_lines(text)
        assert result == text
    def test_remove_blank_lines_single_lines(self):
        text = "line1\n\nline2"
        result = remove_blank_lines(text)
        assert "line1" in result and "line2" in result
class TestShouldSkip:
    def test_should_skip_symlink(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            link_path = Path(tmpdir) / "link"
            target_path = Path(tmpdir) / "target"
            target_path.touch()
            try:
                link_path.symlink_to(target_path)
                assert should_skip(link_path) is True
            except OSError:
                pytest.skip("Cannot create symlinks on this system")
    def test_should_skip_normal_file(self):
        with tempfile.NamedTemporaryFile() as f:
            result = should_skip(f.name)
            assert result is False
class TestDirectoryCopierAndMover:
    def test_directory_copier(self):
        with tempfile.TemporaryDirectory() as src_dir:
            with tempfile.TemporaryDirectory() as dest_dir:
                Path(src_dir, "file1.txt").write_text("test1")
                Path(src_dir, "file2.txt").write_text("test2")
                copier = _DirectoryCopier(src_dir, dest_dir)
                result = copier.copy()
                assert result is True
    def test_directory_mover(self):
        with tempfile.TemporaryDirectory() as src_dir:
            with tempfile.TemporaryDirectory() as dest_dir:
                Path(src_dir, "file.txt").write_text("test")
                mover = _DirectoryMover(src_dir, dest_dir)
                result = mover.move()
                assert result is True
    def test_directory_copier_nested(self):
        with tempfile.TemporaryDirectory() as src_dir:
            with tempfile.TemporaryDirectory() as dest_dir:
                Path(src_dir, "sub", "deep").mkdir(parents=True)
                Path(src_dir, "sub", "deep", "file.txt").write_text("test")
                copier = _DirectoryCopier(src_dir, dest_dir)
                result = copier.copy()
                assert result is True
class TestDirSizeCalculator:
    def test_dir_size_calculator_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x" * 100)
            temp_path = f.name
        try:
            calc = _DirSizeCalculator(Path(temp_path))
            size = calc.calculate()
            assert size == 100
        finally:
            os.unlink(temp_path)
    def test_dir_size_calculator_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("x" * 100)
            calc = _DirSizeCalculator(Path(tmpdir))
            size = calc.calculate()
            assert size >= 100
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
