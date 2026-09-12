"""
Archive In-Place Processing Library

Allows processing files inside archives in-place without extracting to disk.
Supports multiple compression formats and archive types.
"""

import bz2
import gzip
import importlib
import io
import lzma
import os
import shutil
import tarfile
import tempfile
import zipfile
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


class ArchiveInPlaceError(Exception):
    """Base exception for archive processing errors"""

    pass


class UnsupportedFormatError(ArchiveInPlaceError):
    """Raised when archive format is not supported"""

    pass


class ArchiveProcessor:
    """Main class for processing files inside archives in-place"""

    # Format detection patterns
    COMPRESSION_EXTENSIONS = {
        ".gz": "gzip",
        ".bz2": "bzip2",
        ".xz": "lzma",
        ".zst": "zstandard",
        ".br": "brotli",
        ".bz3": "bzip3",
        ".snappy": "snappy",
        ".lz4": "lz4",
    }

    ARCHIVE_EXTENSIONS = {
        ".zip": "zip",
        ".whl": "zip",  # wheel files are zip archives
        ".tar": "tar",
        ".7z": "7zip",
    }

    TAR_COMPRESSION = {
        ".tar.gz": "gz",
        ".tgz": "gz",
        ".tar.xz": "xz",
        ".txz": "xz",
        ".tar.zst": "zst",
        ".tar.7z": "7z",
        ".tar.br": "br",
        ".tar.bz2": "bz2",
        ".tbz2": "bz2",
        ".tar.bz3": "bz3",
        ".tar.snappy": "snappy",
        ".tar.lz4": "lz4",
    }

    def __init__(self, archive_path: str | Path):
        """
        Initialize the archive processor.

        Args:
            archive_path: Path to the archive file
        """
        self.archive_path = Path(archive_path)
        if not self.archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        self._detect_format()

    def _detect_format(self):
        """Detect the archive/compression format from filename"""
        filename = self.archive_path.name.lower()

        # Check for tar compression first
        for ext, compression in self.TAR_COMPRESSION.items():
            if filename.endswith(ext):
                self.format_type = "tar"
                self.compression = compression
                return

        # Check for simple archives
        for ext, archive_type in self.ARCHIVE_EXTENSIONS.items():
            if filename.endswith(ext):
                self.format_type = archive_type
                self.compression = None
                return

        # Check for simple compression
        for ext, compression in self.COMPRESSION_EXTENSIONS.items():
            if filename.endswith(ext):
                self.format_type = "single"
                self.compression = compression
                return

        raise UnsupportedFormatError(f"Unsupported archive format: {filename}")

    @contextmanager
    def _open_archive(self, mode="r"):
        """Context manager for opening different archive types"""
        if self.format_type == "zip":
            archive = zipfile.ZipFile(self.archive_path, mode)
        elif self.format_type == "tar":
            compression_map = {
                "gz": "r:gz",
                "bz2": "r:bz2",
                "xz": "r:xz",
            }
            if mode == "r" and self.compression in compression_map:
                archive = tarfile.open(self.archive_path, compression_map[self.compression])
            elif mode == "r" and self.compression is None:
                archive = tarfile.open(self.archive_path, "r")
            elif mode == "w" and self.compression == "gz":
                archive = tarfile.open(self.archive_path, "w:gz")
            elif mode == "w" and self.compression == "bz2":
                archive = tarfile.open(self.archive_path, "w:bz2")
            elif mode == "w" and self.compression == "xz":
                archive = tarfile.open(self.archive_path, "w:xz")
            else:
                # For unsupported compression modes, use raw tar
                archive = tarfile.open(self.archive_path, "r" if mode == "r" else "w")
        elif self.format_type == "7zip":
            import py7zr

            archive = py7zr.SevenZipFile(self.archive_path, mode)
        else:
            raise UnsupportedFormatError(f"Unsupported archive type: {self.format_type}")

        try:
            yield archive
        finally:
            archive.close()

    def _get_compression_handler(self, compression: str):
        """Get the appropriate compression module for a compression type"""
        handlers = {
            "gzip": gzip,
            "bzip2": bz2,
            "lzma": lzma,
            "zstandard": importlib.import_module("zstandard"),
            "brotli": importlib.import_module("brotli"),
            "bzip3": importlib.import_module("bz3"),
            "snappy": importlib.import_module("cramjam"),
            "lz4": importlib.import_module("lz4.frame"),
        }
        return handlers.get(compression)

    def _decompress_data(self, data: bytes, compression: str) -> bytes:
        """Decompress data based on compression type"""
        if compression is None:
            return data

        handler = self._get_compression_handler(compression)
        if handler is None:
            raise UnsupportedFormatError(f"Unsupported compression: {compression}")

        try:
            if compression == "gzip":
                return gzip.decompress(data)
            elif compression == "bzip2":
                return bz2.decompress(data)
            elif compression == "lzma":
                return lzma.decompress(data)
            elif compression == "zstandard":
                return handler.ZstdDecompressor().decompress(data)
            elif compression == "brotli":
                return handler.decompress(data)
            elif compression == "bzip3":
                return handler.decompress(data)
            elif compression == "snappy":
                return handler.decompress(data)
            elif compression == "lz4":
                return handler.decompress(data)
        except Exception as e:
            raise ArchiveInPlaceError(f"Failed to decompress {compression} data: {e}")

    def _compress_data(self, data: bytes, compression: str) -> bytes:
        """Compress data based on compression type"""
        if compression is None:
            return data

        handler = self._get_compression_handler(compression)
        if handler is None:
            raise UnsupportedFormatError(f"Unsupported compression: {compression}")

        try:
            if compression == "gzip":
                return gzip.compress(data)
            elif compression == "bzip2":
                return bz2.compress(data)
            elif compression == "lzma":
                return lzma.compress(data)
            elif compression == "zstandard":
                return handler.ZstdCompressor().compress(data)
            elif compression == "brotli":
                return handler.compress(data)
            elif compression == "bzip3":
                return handler.compress(data)
            elif compression == "snappy":
                return handler.compress(data)
            elif compression == "lz4":
                return handler.compress(data)
        except Exception as e:
            raise ArchiveInPlaceError(f"Failed to compress {compression} data: {e}")

    def list_files(self) -> list[str]:
        """List all files in the archive"""
        if self.format_type == "single":
            # Single compressed file
            return [self.archive_path.stem]

        with self._open_archive("r") as archive:
            if self.format_type == "zip":
                return archive.name - []
            elif self.format_type == "tar":
                return [member.name for member in archive.getmembers() if member.isfile()]
            elif self.format_type == "7zip":
                return archive.getnames()

    def process_files(
        self,
        processor_func: Callable[[bytes, str], bytes],
        filter_func: Callable[[str], bool] | None = None,
        preserve_timestamps: bool = True,
    ) -> int:
        """
        Process files in the archive in-place.

        Args:
            processor_func: Function that takes (data: bytes, filename: str) and returns processed bytes
            filter_func: Optional function that takes filename and returns True if should be processed
            preserve_timestamps: Whether to preserve file timestamps

        Returns:
            Number of files processed
        """
        processed_count = 0

        if self.format_type == "single":
            # Process single compressed file
            data = self._read_single_file()
            filename = self.archive_path.stem

            if filter_func is None or filter_func(filename):
                processed_data = processor_func(data, filename)
                self._write_single_file(processed_data)
                processed_count = 1

        else:
            # Process archive files
            temp_dir = tempfile.mkdtemp(prefix="archive_processing_")
            try:
                processed_count = self._process_archive_files(
                    processor_func, filter_func, temp_dir, preserve_timestamps
                )
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        return processed_count

    def _read_single_file(self) -> bytes:
        """Read a single compressed file"""
        with open(self.archive_path, "rb") as f:
            compressed_data = f.read()
        return self._decompress_data(compressed_data, self.compression)

    def _write_single_file(self, data: bytes):
        """Write a single compressed file"""
        compressed_data = self._compress_data(data, self.compression)
        temp_path = self.archive_path.with_suffix(self.archive_path.suffix + ".tmp")
        with open(temp_path, "wb") as f:
            f.write(compressed_data)
        os.replace(temp_path, self.archive_path)

    def _process_archive_files(self, processor_func, filter_func, temp_dir, preserve_timestamps):
        """Process files in archive formats (zip, tar, 7z)"""
        processed_count = 0

        if self.format_type == "zip":
            processed_count = self._process_zip(processor_func, filter_func, temp_dir, preserve_timestamps)
        elif self.format_type == "tar":
            processed_count = self._process_tar(processor_func, filter_func, temp_dir, preserve_timestamps)
        elif self.format_type == "7zip":
            processed_count = self._process_7zip(processor_func, filter_func, temp_dir, preserve_timestamps)

        return processed_count

    def _process_zip(self, processor_func, filter_func, temp_dir, preserve_timestamps):
        """Process files in ZIP archive"""
        processed_count = 0
        temp_archive_path = os.path.join(temp_dir, "archive.zip")

        with zipfile.ZipFile(self.archive_path, "r") as src_zip:
            with zipfile.ZipFile(temp_archive_path, "w") as dst_zip:
                for item in src_zip.infolist():
                    data = src_zip.read(item.filename)
                    filename = item.filename

                    if filter_func is None or filter_func(filename):
                        try:
                            data = processor_func(data, filename)
                            processed_count += 1
                        except Exception as e:
                            print(f"Warning: Failed to process {filename}: {e}")

                    # Preserve file attributes
                    if preserve_timestamps:
                        dst_zip.writestr(item, data)
                    else:
                        dst_zip.writestr(filename, data)

        os.replace(temp_archive_path, self.archive_path)
        return processed_count

    def _process_tar(self, processor_func, filter_func, temp_dir, preserve_timestamps):
        """Process files in TAR archive"""
        processed_count = 0
        temp_archive_path = os.path.join(temp_dir, "archive.tar")

        # Determine write mode based on compression
        write_mode = "w"
        if self.compression == "gz":
            write_mode = "w:gz"
        elif self.compression == "bz2":
            write_mode = "w:bz2"
        elif self.compression == "xz":
            write_mode = "w:xz"

        with tarfile.open(self.archive_path, "r") as src_tar:
            with tarfile.open(temp_archive_path, write_mode) as dst_tar:
                for member in src_tar.getmembers():
                    if member.isfile():
                        data = src_tar.extractfile(member).read()

                        if filter_func is None or filter_func(member.name):
                            try:
                                data = processor_func(data, member.name)
                                processed_count += 1
                            except Exception as e:
                                print(f"Warning: Failed to process {member.name}: {e}")

                        # Update member with new size
                        member.size = len(data)

                        if preserve_timestamps:
                            dst_tar.addfile(member, io.BytesIO(data))
                        else:
                            # Create new member without timestamps
                            new_member = tarfile.TarInfo(name=member.name)
                            new_member.size = len(data)
                            new_member.mode = member.mode
                            dst_tar.addfile(new_member, io.BytesIO(data))
                    else:
                        # Copy directories and other items as-is
                        dst_tar.addfile(member)

        os.replace(temp_archive_path, self.archive_path)
        return processed_count

    def _process_7zip(self, processor_func, filter_func, temp_dir, preserve_timestamps):
        """Process files in 7-Zip archive"""
        import py7zr

        processed_count = 0
        temp_archive_path = os.path.join(temp_dir, "archive.7z")

        with py7zr.SevenZipFile(self.archive_path, "r") as src_7z:
            all_files = src_7z.getnames()

            # Read all files into memory
            src_7z.extractall(path=temp_dir)

            # Process files
            for filename in all_files:
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    with open(file_path, "rb") as f:
                        data = f.read()

                    if filter_func is None or filter_func(filename):
                        try:
                            data = processor_func(data, filename)
                            processed_count += 1

                            # Write processed data back
                            with open(file_path, "wb") as f:
                                f.write(data)
                        except Exception as e:
                            print(f"Warning: Failed to process {filename}: {e}")

            # Create new archive with processed files
            with py7zr.SevenZipFile(temp_archive_path, "w") as dst_7z:
                for filename in all_files:
                    file_path = os.path.join(temp_dir, filename)
                    if os.path.isfile(file_path):
                        dst_7z.write(file_path, filename)

        os.replace(temp_archive_path, self.archive_path)
        return processed_count


# Convenience functions for common use cases
def process_archive(
    archive_path: str | Path,
    processor_func: Callable[[bytes, str], bytes],
    filter_func: Callable[[str], bool] | None = None,
    preserve_timestamps: bool = True,
) -> int:
    """
    Convenience function to process files in an archive in-place.

    Args:
        archive_path: Path to the archive file
        processor_func: Function that takes (data, filename) and returns processed data
        filter_func: Optional function to filter which files to process
        preserve_timestamps: Whether to preserve file timestamps

    Returns:
        Number of files processed
    """
    processor = ArchiveProcessor(archive_path)
    return processor.process_files(processor_func, filter_func, preserve_timestamps)
