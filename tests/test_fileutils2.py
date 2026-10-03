from __future__ import annotations

import pytest
import tempfile
import time
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import StringIO
import sys

import sys
sys.path.insert(0, str(Path(__file__).parent))

from dh import (
    read_lines,
    read_lines_mmap,
    gext,
    get_dirs,
    get_file_age,
    get_installed_packages,
    get_installed_pkgs,
    get_mime_type,
    get_random_filename,
    is_image,
    is_within,
    normalize_filename,
    normalize_path,
    reverse_dict,
    fsz,
    safe_delete,
    get_filez,
    unique_path,
    format_time,
    runcmd,
    write_txt_file,
    should_skip,
    append_text,
    get_removed_lines,
    restore_bak,
    is_empty,
    get_files_scandir,
    get_files,
    get_nobinary,
    get_pyfiles,
    walk_paths,
    is_text_file,
    atomic_write,
    walk_files,
    walkfiles,
    gsze,
    FileWalkerConfig,
    get_files_iter_config,
    ReportGenerator,
    ReportItem,
    remove_blank_lines,
    is_python_file,
    _FileReader,
    _ExtensionAnalyzer,
    _FileAgeCalculator,
    _FileSizeFormatter,
    _DirectoryWalker,
    _UniquePathFinder,
    _TimeFormatter,
    _CommandRunner,
    _FileCollector,
    _BFSFileWalker,
    _ConfigurableFileWalker,
    _DirSizeCalculator,
    _DirectoryCopier,
    _DirectoryMover,
    _PythonFileChecker,
    _PythonFileFinder,
    _PathWalker,
    _FileProcessor,
    _TextFileDeterminer,
    _SizeByExtensionCalculator,
    _check_binary_chunk,
)


class TestFileReader:
    """Tests for file reading functionality"""
    
    def test_read_lines_simple_file(self):
        """Test reading lines from a simple file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
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
        """Test reading lines with line endings preserved"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("line1\nline2\n")
            temp_path = f.name
        try:
            lines = read_lines(temp_path, ke=True)
            assert lines[0].endswith("\n")
        finally:
            os.unlink(temp_path)

    def test_read_lines_mmap(self):
        """Test reading large files with memory mapping"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("x" * 10000)
            temp_path = f.name
        try:
            lines = read_lines_mmap(Path(temp_path), keep_ends=False)
            assert len(lines) > 0
        finally:
            os.unlink(temp_path)

    def test_file_reader_class(self):
        """Test FileReader class directly"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("test\ndata")
            temp_path = f.name
        try:
            reader = _FileReader(temp_path, keep_ends=False)
            lines = reader.read()
            assert len(lines) == 2
        finally:
            os.unlink(temp_path)

    def test_read_lines_empty_file(self):
        """Test reading an empty file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name
        try:
            lines = read_lines(temp_path, ke=False)
            assert isinstance(lines, list)
        finally:
            os.unlink(temp_path)

    def test_read_lines_with_special_chars(self):
        """Test reading files with special characters and UTF-8"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as f:
            f.write("测试\nтест\n日本語")
            temp_path = f.name
        try:
            lines = read_lines(temp_path, ke=False)
            assert len(lines) >= 2
        finally:
            os.unlink(temp_path)


class TestExtensionAnalyzer:
    """Tests for file extension analysis"""
    
    def test_single_extension(self):
        """Test single extension detection"""
        analyzer = _ExtensionAnalyzer("file.txt")
        assert analyzer.analyze() == ".txt"

    def test_no_extension(self):
        """Test files without extensions"""
        analyzer = _ExtensionAnalyzer("Makefile")
        assert analyzer.analyze() == ""

    def test_multipart_extension_tar(self):
        """Test tar.gz and similar multipart extensions"""
        analyzer = _ExtensionAnalyzer("archive.tar.gz")
        result = analyzer.analyze()
        assert result in [".tar.gz", ".gz"]

    def test_gext_function(self):
        """Test gext function"""
        assert gext("file.py") == ".py"
        assert gext("archive.tar.gz") in [".tar.gz", ".gz"]

    def test_double_extension(self):
        """Test double extensions like .min.js"""
        analyzer = _ExtensionAnalyzer("script.min.js")
        result = analyzer.analyze()
        assert ".js" in result

    def test_many_dots_in_filename(self):
        """Test filenames with many dots"""
        analyzer = _ExtensionAnalyzer("my.file.name.with.many.dots.txt")
        result = analyzer.analyze()
        assert ".txt" in result


class TestDirectoryWalker:
    """Tests for directory walking functionality"""
    
    def test_get_dirs_simple(self):
        """Test getting directories in a simple structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir1 = Path(tmpdir) / "sub1"
            subdir2 = Path(tmpdir) / "sub2"
            subdir1.mkdir()
            subdir2.mkdir()
            
            dirs = get_dirs(tmpdir)
            assert len(dirs) >= 2

    def test_get_dirs_nested(self):
        """Test getting directories in nested structures"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a", "b", "c").mkdir(parents=True)
            dirs = get_dirs(tmpdir)
            assert len(dirs) >= 3

    def test_get_dirs_non_directory(self):
        """Test get_dirs on a file path"""
        with tempfile.NamedTemporaryFile() as f:
            dirs = get_dirs(f.name)
            assert dirs == []

    def test_get_dirs_empty_directory(self):
        """Test get_dirs on empty directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            dirs = get_dirs(tmpdir)
            assert dirs == []

    def test_directory_walker_class(self):
        """Test DirectoryWalker class"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "sub1").mkdir()
            Path(tmpdir, "sub2").mkdir()
            walker = _DirectoryWalker(tmpdir)
            dirs = walker.walk()
            assert len(dirs) >= 2


class TestFileAgeCalculator:
    """Tests for file age calculation"""
    
    def test_file_age_non_existent(self):
        """Test file age for non-existent files"""
        age = get_file_age("/nonexistent/path")
        assert age == 0.0

    def test_file_age_recent_file(self):
        """Test file age for recently created files"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            age = get_file_age(temp_path)
            assert age >= 0
        finally:
            os.unlink(temp_path)

    def test_file_age_string_format(self):
        """Test file age in string format"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            age_str = get_file_age(temp_path, str_mode=True)
            assert isinstance(age_str, str)
            assert "sec" in age_str or age_str == "0 sec"
        finally:
            os.unlink(temp_path)

    def test_age_calculator_class(self):
        """Test FileAgeCalculator class"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            calc = _FileAgeCalculator(temp_path)
            assert calc.as_float() >= 0
            assert isinstance(calc.as_string(), str)
        finally:
            os.unlink(temp_path)

    def test_file_age_old_file(self):
        """Test file age calculation for older files"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            os.utime(temp_path, (0, 0))
            age_str = get_file_age(temp_path, str_mode=True)
            assert isinstance(age_str, str)
        finally:
            os.unlink(temp_path)


class TestPackageUtilities:
    """Tests for package utility functions"""
    
    @patch('importlib.metadata.distributions')
    def test_get_installed_packages(self, mock_distributions):
        """Test retrieving installed packages"""
        mock_dist = MagicMock()
        mock_dist.metadata.get.side_effect = lambda x: {
            "Name": "test-package",
            "Version": "1.0.0"
        }.get(x)
        mock_distributions.return_value = [mock_dist]
        
        packages = get_installed_packages()
        assert isinstance(packages, dict)

    @patch('importlib.metadata.distributions')
    def test_get_installed_pkgs(self, mock_distributions):
        """Test retrieving installed package list"""
        mock_dist = MagicMock()
        mock_dist.metadata.get.return_value = "test-package"
        mock_distributions.return_value = [mock_dist]
        
        pkgs = get_installed_pkgs()
        assert isinstance(pkgs, list)

    @patch('importlib.metadata.distributions')
    def test_get_installed_packages_with_none(self, mock_distributions):
        """Test handling packages with missing metadata"""
        mock_dist = MagicMock()
        mock_dist.metadata.get.return_value = None
        mock_distributions.return_value = [mock_dist]
        
        packages = get_installed_packages()
        assert isinstance(packages, dict)


class TestMimeAndImage:
    """Tests for MIME type and image detection"""
    
    def test_get_mime_type_text(self):
        """Test MIME type detection for text files"""
        mime = get_mime_type("file.txt")
        assert mime in ["text/plain", None]

    def test_get_mime_type_python(self):
        """Test MIME type detection for Python files"""
        mime = get_mime_type("file.py")
        assert mime in ["text/x-python", "text/plain", None]

    def test_is_image_false(self):
        """Test is_image returns False for non-image files"""
        with tempfile.NamedTemporaryFile(suffix='.txt') as f:
            result = is_image(f.name)
            assert result is False

    def test_is_image_exception_handling(self):
        """Test is_image handles exceptions gracefully"""
        result = is_image("/nonexistent/path/file.jpg")
        assert result is False


class TestRandomFilename:
    """Tests for random filename generation"""
    
    def test_get_random_filename_default_length(self):
        """Test random filename with default length"""
        name = get_random_filename()
        assert len(name) == 10
        assert name.islower()

    def test_get_random_filename_custom_length(self):
        """Test random filename with custom length"""
        name = get_random_filename(length=20)
        assert len(name) == 20

    def test_get_random_filename_uniqueness(self):
        """Test that random filenames are unique"""
        names = [get_random_filename() for _ in range(10)]
        assert len(set(names)) == 10


class TestPathUtilities:
    """Tests for path utility functions"""
    
    def test_is_within_true(self):
        """Test is_within for child path inside parent"""
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            child = parent / "subdir"
            child.mkdir()
            assert is_within(child, parent)

    def test_is_within_false(self):
        """Test is_within for unrelated paths"""
        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                assert not is_within(tmpdir1, tmpdir2)

    def test_is_within_same_path(self):
        """Test is_within with same path"""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert is_within(tmpdir, tmpdir)

    def test_normalize_filename(self):
        """Test filename normalization"""
        result = normalize_filename('file<name>.txt')
        assert '<' not in result and '>' not in result

    def test_normalize_filename_special_chars(self):
        """Test normalization of various special characters"""
        result = normalize_filename('file|name*?.txt')
        assert '|' not in result and '*' not in result and '?' not in result

    def test_normalize_path(self):
        """Test path normalization"""
        result = normalize_path(".")
        assert isinstance(result, Path)


class TestDictUtilities:
    """Tests for dictionary utility functions"""
    
    def test_reverse_dict_simple(self):
        """Test simple dictionary reversal"""
        d = {"a": 1, "b": 2}
        rev = reverse_dict(d)
        assert rev[1] == "a"
        assert rev[2] == "b"

    def test_reverse_dict_duplicate_values(self):
        """Test dictionary reversal with duplicate values"""
        d = {"a": 1, "b": 1}
        rev = reverse_dict(d)
        assert 1 in rev

    def test_reverse_dict_empty(self):
        """Test reversing empty dictionary"""
        rev = reverse_dict({})
        assert rev == {}


class TestFileSizeFormatter:
    """Tests for file size formatting"""
    
    def test_fsz_bytes(self):
        """Test file size formatting in bytes"""
        result = fsz(512)
        assert "B" in result

    def test_fsz_kilobytes(self):
        """Test file size formatting in kilobytes"""
        result = fsz(1024)
        assert "KB" in result

    def test_fsz_megabytes(self):
        """Test file size formatting in megabytes"""
        result = fsz(1024 * 1024)
        assert "MB" in result

    def test_fsz_gigabytes(self):
        """Test file size formatting in gigabytes"""
        result = fsz(1024 * 1024 * 1024)
        assert "GB" in result

    def test_fsz_zero(self):
        """Test file size formatting for zero"""
        result = fsz(0)
        assert result == "0 B"

    def test_fsz_negative(self):
        """Test file size formatting for negative numbers"""
        result = fsz(-1024)
        assert "KB" in result

    def test_file_size_formatter_class(self):
        """Test FileSizeFormatter class"""
        formatter = _FileSizeFormatter()
        result = formatter.format(2048)
        assert "KB" in result


class TestSafeDelete:
    """Tests for safe delete functionality"""
    
    def test_safe_delete_file(self):
        """Test safe deletion of a file"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = Path(f.name)
        result = safe_delete(temp_path)
        assert result is True
        assert not temp_path.exists()

    def test_safe_delete_directory(self):
        """Test safe deletion of a directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            result = safe_delete(path)
            assert result is True

    def test_safe_delete_nonexistent(self):
        """Test safe delete on non-existent path"""
        result = safe_delete(Path("/nonexistent/path"))
        assert result is False


class TestUniquePathFinder:
    """Tests for unique path finding"""
    
    def test_unique_path_not_exists(self):
        """Test unique path for non-existent file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "newfile.txt"
            result = unique_path(path)
            assert str(result) == str(path)

    def test_unique_path_exists(self):
        """Test unique path generation for existing file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            path.write_text("test")
            result = unique_path(path)
            assert result != path
            assert "_1" in result.name

    def test_unique_path_multiple_exists(self):
        """Test unique path with multiple existing files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            path.write_text("test")
            (Path(tmpdir) / "file_1.txt").write_text("test")
            result = unique_path(path)
            assert "_2" in result.name

    def test_unique_path_finder_class(self):
        """Test UniquePathFinder class"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            finder = _UniquePathFinder(path)
            result = finder.find()
            assert isinstance(result, Path)


class TestTimeFormatter:
    """Tests for time formatting"""
    
    def test_format_seconds(self):
        """Test formatting time in seconds"""
        result = format_time(30)
        assert "30s" in result or "s" in result

    def test_format_minutes(self):
        """Test formatting time in minutes"""
        result = format_time(150)
        assert "m" in result

    def test_format_hours(self):
        """Test formatting time in hours"""
        result = format_time(3700)
        assert "h" in result

    def test_format_days(self):
        """Test formatting time in days"""
        result = format_time(86400 + 3600)
        assert "d" in result or "h" in result

    def test_format_zero(self):
        """Test formatting zero time"""
        result = format_time(0)
        assert result == "0s"

    def test_format_microseconds(self):
        """Test formatting microseconds"""
        result = format_time(0.0001)
        assert "µs" in result or "ms" in result

    def test_time_formatter_class(self):
        """Test TimeFormatter class"""
        result = _TimeFormatter.format(45)
        assert isinstance(result, str)


class TestCommandRunner:
    """Tests for command execution"""
    
    def test_runcmd_simple(self):
        """Test simple command execution"""
        code, stdout, stderr = runcmd(['echo', 'hello'], run_silently=False)
        assert code == 0

    def test_runcmd_silent(self):
        """Test silent command execution"""
        code, stdout, stderr = runcmd(['echo', 'hello'], run_silently=True)
        assert code == 0
        assert stdout == ""

    def test_runcmd_timeout(self):
        """Test command execution with timeout"""
        code, stdout, stderr = runcmd(['sleep', '10'], timeout=0.1, run_silently=True)
        assert code in [124, -15, 143]

    def test_runcmd_nonexistent(self):
        """Test command execution with non-existent command"""
        code, stdout, stderr = runcmd(['/nonexistent/command'], run_silently=True)
        assert code == 127

    def test_runcmd_empty_list(self):
        """Test command execution with empty list"""
        with pytest.raises(ValueError):
            runcmd([])

    def test_command_runner_class(self):
        """Test CommandRunner class"""
        runner = _CommandRunner(['echo', 'test'], run_silently=True)
        code, stdout, stderr = runner.run()
        assert code == 0


class TestTextFileOperations:
    """Tests for text file operations"""
    
    def test_write_txt_file(self):
        """Test writing text to file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            result = write_txt_file(path, "test content")
            assert result is True
            assert path.read_text() == "test content"

    def test_write_txt_file_existing_no_overwrite(self):
        """Test writing to existing file without overwrite"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            path.write_text("original")
            result = write_txt_file(path, "new", overwrite=False)
            assert result is False

    def test_write_txt_file_non_string(self):
        """Test writing non-string data to file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            result = write_txt_file(path, 123)
            assert result is False

    def test_append_text(self):
        """Test appending text to file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            path.write_text("line1")
            result = append_text(path, "line2")
            assert result is True
            assert "line2" in path.read_text()

    def test_append_text_new_file(self):
        """Test appending to non-existent file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            result = append_text(path, "content")
            assert result is True

    def test_append_text_directory(self):
        """Test appending to directory path"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = append_text(tmpdir, "content")
            assert result is False


class TestFileDiffUtilities:
    """Tests for file diff utilities"""
    
    def test_get_removed_lines(self):
        """Test getting removed lines between two texts"""
        txt1 = "line1\nline2\nline3"
        txt2 = "line1\nline3"
        removed = get_removed_lines(txt1, txt2)
        assert "line2" in removed

    def test_get_removed_lines_empty(self):
        """Test getting removed lines with no changes"""
        removed = get_removed_lines("same", "same")
        assert len(removed) == 0

    def test_get_removed_lines_all_removed(self):
        """Test getting removed lines with all lines removed"""
        removed = get_removed_lines("line1\nline2", "")
        assert len(removed) == 2


class TestBackupUtilities:
    """Tests for backup functionality"""
    
    def test_restore_bak(self):
        """Test restoring from backup file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            bak_path = Path(tmpdir) / "file.txt.bak"
            bak_path.write_text("backup content")
            
            result = restore_bak(path)
            assert result is True
            assert path.read_text() == "backup content"

    def test_restore_bak_no_backup(self):
        """Test restoring when no backup exists"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            result = restore_bak(path)
            assert result is False


class TestDirectoryQueries:
    """Tests for directory query functions"""
    
    def test_is_empty_true(self):
        """Test is_empty for empty directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = is_empty(tmpdir)
            assert result is True

    def test_is_empty_false(self):
        """Test is_empty for non-empty directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("test")
            result = is_empty(tmpdir)
            assert result is False

    def test_is_empty_file(self):
        """Test is_empty on file path"""
        with tempfile.NamedTemporaryFile() as f:
            result = is_empty(f.name)
            assert result is False


class TestFileCollector:
    """Tests for file collection"""
    
    def test_get_files_scandir(self):
        """Test file collection with scandir"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").write_text("test")
            Path(tmpdir, "file2.txt").write_text("test")
            files = get_files_scandir(tmpdir, ext=[".txt"])
            assert len(files) >= 2

    def test_get_files_scandir_hidden(self):
        """Test file collection excluding hidden files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".hidden").write_text("test")
            Path(tmpdir, "visible.txt").write_text("test")
            files = get_files_scandir(tmpdir, include_hidden=False)
            assert all(not f.name.startswith('.') for f in files)

    def test_file_collector_class(self):
        """Test FileCollector class"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.txt").write_text("test")
            collector = _FileCollector(tmpdir, ext=[".txt"])
            files = collector.collect()
            assert len(files) >= 1

    def test_get_files(self):
        """Test get_files function"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "sub").mkdir()
            Path(tmpdir, "sub", "file.txt").write_text("test")
            files = get_files(tmpdir, ext=[".txt"])
            assert len(files) >= 1


class TestBFSFileWalker:
    """Tests for BFS file walker"""
    
    def test_bfs_file_walker(self):
        """Test BFS file walker"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "level1", "level2").mkdir(parents=True)
            Path(tmpdir, "level1", "level2", "file.txt").write_text("test")
            walker = _BFSFileWalker(tmpdir, ext=[".txt"])
            files = walker.walk()
            assert len(files) >= 1


class TestPythonFileDetection:
    """Tests for Python file detection"""
    
    def test_is_python_file_py_extension(self):
        """Test Python file detection by .py extension"""
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("print('hello')")
            temp_path = f.name
        try:
            result = is_python_file(temp_path)
            assert result is True
        finally:
            os.unlink(temp_path)

    def test_is_python_file_no_extension(self):
        """Test Python file detection for shebang scripts"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("#!/usr/bin/env python3\nprint('hello')")
            temp_path = f.name
        try:
            result = is_python_file(temp_path)
            assert isinstance(result, bool)
        finally:
            os.unlink(temp_path)

    def test_python_file_checker_class(self):
        """Test PythonFileChecker class"""
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write("x = 1")
            temp_path = f.name
        try:
            checker = _PythonFileChecker(temp_path)
            assert checker.is_python_file() is True
        finally:
            os.unlink(temp_path)

    def test_get_pyfiles(self):
        """Test get_pyfiles function"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "script.py").write_text("print('test')")
            files = get_pyfiles(tmpdir)
            assert len(files) >= 1

    def test_get_pyfiles_nested(self):
        """Test get_pyfiles with nested directories"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "sub", "deep").mkdir(parents=True)
            Path(tmpdir, "sub", "deep", "script.py").write_text("x = 1")
            files = get_pyfiles(tmpdir)
            assert len(files) >= 1


class TestTextFileDetermination:
    """Tests for text file determination"""
    
    def test_is_text_file_true(self):
        """Test text file detection"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("plain text")
            temp_path = f.name
        try:
            result = is_text_file(temp_path)
            assert isinstance(result, bool)
        finally:
            os.unlink(temp_path)

    def test_text_file_determiner_class(self):
        """Test TextFileDeterminer class"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("text content")
            temp_path = f.name
        try:
            determiner = _TextFileDeterminer(temp_path)
            result = determiner.is_text()
            assert isinstance(result, bool)
        finally:
            os.unlink(temp_path)

    def test_is_text_file_nonexistent(self):
        """Test is_text_file with non-existent path"""
        with pytest.raises(FileNotFoundError):
            is_text_file("/nonexistent/file.txt")


class TestBinaryChunkChecking:
    """Tests for binary chunk detection"""
    
    def test_check_binary_chunk_null_bytes(self):
        """Test binary detection with null bytes"""
        chunk = b"binary\x00data\x00here"
        result = _check_binary_chunk(chunk)
        assert isinstance(result, bool)

    def test_check_binary_chunk_text(self):
        """Test binary detection for text"""
        chunk = b"plain text content"
        result = _check_binary_chunk(chunk)
        assert result is False

    def test_check_binary_chunk_empty(self):
        """Test binary detection for empty chunk"""
        result = _check_binary_chunk(b"")
        assert result is False

    def test_check_binary_chunk_mostly_binary(self):
        """Test binary detection for mostly binary data"""
        chunk = bytes(range(256)) * 10
        result = _check_binary_chunk(chunk)
        assert isinstance(result, bool)


class TestAtomicWrite:
    """Tests for atomic file writing"""
    
    def test_atomic_write(self):
        """Test atomic file writing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            atomic_write(path, "atomic content")
            assert path.read_text() == "atomic content"

    def test_atomic_write_overwrites(self):
        """Test atomic write overwrites existing file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"
            path.write_text("old")
            atomic_write(path, "new")
            assert path.read_text() == "new"

    def test_atomic_write_preserves_parent(self):
        """Test atomic write preserves parent directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "test.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, "content")
            assert path.read_text() == "content"


class TestWalkFiles:
    """Tests for file walking"""
    
    def test_walk_files(self):
        """Test walk_files function"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").write_text("test")
            Path(tmpdir, "file2.py").write_text("test")
            files = walk_files(tmpdir)
            assert len(files) >= 2

    def test_walkfiles_generator(self):
        """Test walkfiles generator"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("test")
            gen = walkfiles(tmpdir)
            items = list(gen)
            assert len(items) >= 1

    def test_walk_files_with_extension(self):
        """Test walk_files with extension filter"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").write_text("test")
            Path(tmpdir, "file2.py").write_text("test")
            files = walk_files(tmpdir, ext=[".txt"])
            assert all(f.suffix == ".txt" for f in files)


class TestDirSize:
    """Tests for directory size calculation"""
    
    def test_gsz_file(self):
        """Test size calculation for single file"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x" * 100)
            temp_path = f.name
        try:
            size = gsz(temp_path)
            assert size == 100
        finally:
            os.unlink(temp_path)

    def test_gsz_directory(self):
        """Test size calculation for directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("x" * 50)
            size = gsz(tmpdir)
            assert size >= 50

    def test_gsze_with_extension(self):
        """Test size calculation filtered by extension"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("x" * 100)
            Path(tmpdir, "file.py").write_text("y" * 50)
            size = gsze(tmpdir, ext=[".txt"])
            assert size >= 100

    def test_size_by_extension_calculator(self):
        """Test SizeByExtensionCalculator class"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("x" * 100)
            calc = _SizeByExtensionCalculator(tmpdir, ext=[".txt"])
            size = calc.calculate()
            assert size >= 100


class TestFileWalkerConfig:
    """Tests for file walker configuration"""
    
    def test_file_walker_config_defaults(self):
        """Test FileWalkerConfig with default values"""
        config = FileWalkerConfig()
        assert config.skip_hidden is False
        assert config.skip_symlinks is True

    def test_file_walker_config_custom(self):
        """Test FileWalkerConfig with custom values"""
        config = FileWalkerConfig(skip_hidden=True, skip_dirs={".git"})
        assert config.skip_hidden is True

    def test_configurable_file_walker(self):
        """Test ConfigurableFileWalker class"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("test")
            config = FileWalkerConfig()
            walker = _ConfigurableFileWalker(tmpdir, config)
            files = list(walker.walk())
            assert len(files) >= 1

    def test_get_files_iter_config(self):
        """Test get_files_iter_config function"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("test")
            config = FileWalkerConfig()
            files = list(get_files_iter_config(tmpdir, config))
            assert len(files) >= 1


class TestPathWalker:
    """Tests for path walker"""
    
    def test_path_walker_single_file(self):
        """Test PathWalker with single file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.txt"
            path.write_text("test")
            walker = _PathWalker(str(path))
            files = list(walker.walk())
            assert len(files) == 1

    def test_path_walker_multiple_paths(self):
        """Test PathWalker with multiple paths"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").write_text("test")
            Path(tmpdir, "file2.txt").write_text("test")
            walker = _PathWalker([Path(tmpdir) / "file1.txt", Path(tmpdir) / "file2.txt"])
            files = list(walker.walk())
            assert len(files) >= 2

    def test_walk_paths_function(self):
        """Test walk_paths function"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("test")
            files = list(walk_paths(tmpdir, ext=[".txt"]))
            assert len(files) >= 1


class TestReportGenerator:
    """Tests for report generation"""
    
    def test_report_item_creation(self):
        """Test ReportItem creation"""
        item = ReportItem(path="test.txt", category="success", message="OK")
        assert item.path == "test.txt"
        assert item.category == "success"

    def test_report_generator_add_item(self):
        """Test adding items to ReportGenerator"""
        gen = ReportGenerator(title="Test Report")
        item = ReportItem(path="file.txt", category="success")
        gen.add_item(item)
        assert len(gen.items) == 1
        assert gen.stats["success"] == 1

    def test_report_generator_add_stat(self):
        """Test adding stats to ReportGenerator"""
        gen = ReportGenerator()
        gen.add_stat("total_files", 10)
        assert gen.stats["total_files"] == 10

    def test_report_generator_print(self, capsys):
        """Test printing report"""
        gen = ReportGenerator(title="Test")
        item = ReportItem(path="file.txt", category="success", message="OK")
        gen.add_item(item)
        gen.print_report()
        captured = capsys.readouterr()
        assert "Test" in captured.out

    def test_report_generator_export_text(self):
        """Test exporting report as text"""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator()
            item = ReportItem(path="file.txt", category="success")
            gen.add_item(item)
            export_path = Path(tmpdir) / "report.txt"
            gen.export_to_file(export_path, format="text")
            assert export_path.exists()

    def test_report_generator_export_csv(self):
        """Test exporting report as CSV"""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator()
            item = ReportItem(path="file.txt", category="success")
            gen.add_item(item)
            export_path = Path(tmpdir) / "report.csv"
            gen.export_to_file(export_path, format="csv")
            assert export_path.exists()

    def test_report_generator_sort_by_path(self):
        """Test sorting report by path"""
        gen = ReportGenerator()
        gen.add_item(ReportItem(path="z.txt", category="success"))
        gen.add_item(ReportItem(path="a.txt", category="success"))
        gen.print_report(sort_by="path")
        assert gen.items[0].path < gen.items[1].path


class TestRemoveBlankLines:
    """Tests for blank line removal"""
    
    def test_remove_blank_lines(self):
        """Test removing consecutive blank lines"""
        text = "line1\n\nline2\n\n\nline3"
        result = remove_blank_lines(text)
        assert result.count("\n\n") == 0

    def test_remove_blank_lines_no_blanks(self):
        """Test with no blank lines"""
        text = "line1\nline2\nline3"
        result = remove_blank_lines(text)
        assert result == text

    def test_remove_blank_lines_single_lines(self):
        """Test with single blank lines"""
        text = "line1\n\nline2"
        result = remove_blank_lines(text)
        assert "line1" in result and "line2" in result


class TestShouldSkip:
    """Tests for path skip logic"""
    
    def test_should_skip_symlink(self):
        """Test skipping symlinks"""
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
        """Test not skipping normal files"""
        with tempfile.NamedTemporaryFile() as f:
            result = should_skip(f.name)
            assert result is False


class TestDirectoryCopierAndMover:
    """Tests for directory copy and move operations"""
    
    def test_directory_copier(self):
        """Test directory copying"""
        with tempfile.TemporaryDirectory() as src_dir:
            with tempfile.TemporaryDirectory() as dest_dir:
                Path(src_dir, "file1.txt").write_text("test1")
                Path(src_dir, "file2.txt").write_text("test2")
                
                copier = _DirectoryCopier(src_dir, dest_dir)
                result = copier.copy()
                assert result is True

    def test_directory_mover(self):
        """Test directory moving"""
        with tempfile.TemporaryDirectory() as src_dir:
            with tempfile.TemporaryDirectory() as dest_dir:
                Path(src_dir, "file.txt").write_text("test")
                
                mover = _DirectoryMover(src_dir, dest_dir)
                result = mover.move()
                assert result is True

    def test_directory_copier_nested(self):
        """Test copying nested directory structure"""
        with tempfile.TemporaryDirectory() as src_dir:
            with tempfile.TemporaryDirectory() as dest_dir:
                Path(src_dir, "sub", "deep").mkdir(parents=True)
                Path(src_dir, "sub", "deep", "file.txt").write_text("test")
                
                copier = _DirectoryCopier(src_dir, dest_dir)
                result = copier.copy()
                assert result is True


class TestDirSizeCalculator:
    """Tests for directory size calculation"""
    
    def test_dir_size_calculator_file(self):
        """Test DirSizeCalculator for single file"""
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
        """Test DirSizeCalculator for directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").write_text("x" * 100)
            calc = _DirSizeCalculator(Path(tmpdir))
            size = calc.calculate()
            assert size >= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
