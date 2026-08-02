import bz2
import gzip
import logging
import lzma
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from io import BufferedReader
from pathlib import Path

import brotli
import py7zr
from lz4.frame import LZ4FrameDecompressor
from zstandard import ZstdDecompressionReader

logger = logging.getLogger(__name__)

_HASH_TABLE_SIZE = 1 << 14
_MAX_OFFSET_1 = 2047
_MAX_OFFSET_2 = 65535


def is_valid_archive(path: (str | Path)) -> bool:
    path = Path(path)
    try:
        if not path.is_file():
            return False
        if not path.stat().st_size:
            return False

        lower = path.name.lower()

        # Standard archives
        if lower.endswith((".zip", ".whl")):
            return _check_zip(path)
        if lower.endswith(".tar"):
            return _check_tar(path, mode="r:")
        if lower.endswith((".tar.gz", ".tgz")):
            return _check_tar(path, mode="r:gz")
        if lower.endswith((".tar.xz", ".txz")):
            return _check_tar(path, mode="r:xz")
        if lower.endswith((".tar.bz2", ".tbz2", ".tbz")):
            return _check_tar(path, mode="r:bz2")

        # Compressed tar files (streaming validation)
        if lower.endswith(".tar.br"):
            return _check_tar_with_brotli(path)
        if lower.endswith(".tar.zst"):
            return _check_tar_with_zstd(path)
        if lower.endswith(".tar.lz4"):
            return _check_tar_with_lz4(path)
        if lower.endswith(".tar.lzma"):
            return _check_tar_with_lzma(path)

        # Single compressed files
        if lower.endswith(".br"):
            return _check_brotli_file(path)
        if lower.endswith(".zst"):
            return _check_zstd_file(path)
        if lower.endswith(".lz4"):
            return _check_lz4_file(path)
        if lower.endswith(".lzma"):
            return _check_lzma_file(path)
        if lower.endswith(".gz"):
            return _check_gzip_file(path)
        if lower.endswith(".bz2"):
            return _check_bz2_file(path)
        if lower.endswith(".xz"):
            return _check_xz_file(path)

        # 7z archives
        if lower.endswith(".7z"):
            return _check_7z_file(path)

        return False
    except Exception as e:
        logger.debug("Archive validation failed for %s: %s", path, e)
        return False


def is_wheel_ok(path: Path) -> bool:
    """Check if a wheel/zip file is valid."""
    try:
        with zipfile.ZipFile(path, "r") as wheel:
            corrupt_file = wheel.testzip()
            return not corrupt_file
    except (zipfile.BadZipFile, FileNotFoundError):
        return False
    except Exception as e:
        logger.debug("Wheel validation failed for %s: %s", path, e)
        return False


def _check_zip(path: Path) -> bool:
    """Validate a zip file (including wheels)."""
    return is_wheel_ok(path)


def _check_tar(path: Path, mode: str) -> bool:
    """Validate a tar file with given compression mode."""
    try:
        with tarfile.open(path, mode) as tf:
            # Check for corruption
            if tf.badfile() is not None:
                return False
            # Try to read members (validates the tar structure)
            tf.getmembers()
            return True
    except (tarfile.TarError, EOFError, IOError) as e:
        logger.debug("Tar validation failed for %s: %s", path, e)
        return False


def _check_gzip_file(path: Path) -> bool:
    """Validate a gzip file by decompressing it."""
    try:
        with gzip.open(path, "rb") as f:
            # Read in chunks to avoid memory issues with large files
            while f.read(65536):
                pass
        return True
    except (gzip.BadGzipFile, EOFError, IOError) as e:
        logger.debug("Gzip validation failed for %s: %s", path, e)
        return False


def _check_bz2_file(path: Path) -> bool:
    """Validate a bzip2 file by decompressing it."""
    try:
        with bz2.open(path, "rb") as f:
            while f.read(65536):
                pass
        return True
    except (EOFError, IOError) as e:
        logger.debug("Bzip2 validation failed for %s: %s", path, e)
        return False


def _check_xz_file(path: Path) -> bool:
    """Validate an xz file by decompressing it."""
    try:
        with lzma.open(path, "rb") as f:
            while f.read(65536):
                pass
        return True
    except (lzma.LZMAError, EOFError, IOError) as e:
        logger.debug("XZ validation failed for %s: %s", path, e)
        return False


def _check_brotli_file(path: Path) -> bool:
    """Validate a brotli file using streaming decompression."""
    try:
        with open(path, "rb") as f:
            decompressor = brotli.Decompressor()
            while True:
                chunk = f.read(65536)
                if not chunk:
                    # Finalize decompression
                    decompressor.flush()
                    break
                decompressor.process(chunk)
        return True
    except Exception as e:
        logger.debug("Brotli validation failed for %s: %s", path, e)
        return False


def _check_zstd_file(path: Path) -> bool:
    """Validate a zstd file using streaming decompression."""
    try:
        import zstandard as zstd

        dctx = zstd.ZstdDecompressor()
        with open(path, "rb") as f:
            reader = dctx.stream_reader(f)
            while reader.read(65536):
                pass
        return True
    except Exception as e:
        logger.debug("Zstd validation failed for %s: %s", path, e)
        return False


def _check_lz4_file(path: Path) -> bool:
    """Validate an LZ4 file using streaming decompression."""
    try:
        with open(path, "rb") as f:
            decompressor = LZ4FrameDecompressor(f)
            while decompressor.read(65536):
                pass
        return True
    except Exception as e:
        logger.debug("LZ4 validation failed for %s: %s", path, e)
        return False


def _check_lzma_file(path: Path) -> bool:
    """Validate an LZMA file using streaming decompression."""
    try:
        with lzma.open(path, "rb") as f:
            while f.read(65536):
                pass
        return True
    except (lzma.LZMAError, EOFError, IOError) as e:
        logger.debug("LZMA validation failed for %s: %s", path, e)
        return False


def _check_7z_file(path: Path) -> bool:
    """Validate a 7z file."""
    try:
        with py7zr.SevenZipFile(path, "r") as szf:
            # Test integrity by reading the archive
            szf.test()
            return True
    except Exception as e:
        logger.debug("7z validation failed for %s: %s", path, e)
        return False


def _check_tar_with_brotli(path: Path) -> bool:
    """Validate a brotli-compressed tar file using streaming."""
    try:
        with open(path, "rb") as f:
            decompressor = brotli.Decompressor()
            # Use a temporary file to avoid loading everything into memory
            with tempfile.TemporaryFile() as tmp:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        tmp.write(decompressor.flush())
                        break
                    tmp.write(decompressor.process(chunk))
                tmp.seek(0)
                with tarfile.open(fileobj=tmp, mode="r|") as tf:
                    # Just iterate through members to validate
                    for _ in tf:
                        pass
        return True
    except Exception as e:
        logger.debug("Tar.brotli validation failed for %s: %s", path, e)
        return False


def _check_tar_with_zstd(path: Path) -> bool:
    """Validate a zstd-compressed tar file using streaming (no extraction to disk)."""
    try:
        import zstandard as zstd

        dctx = zstd.ZstdDecompressor()
        with open(path, "rb") as f:
            reader = dctx.stream_reader(f)
            with tarfile.open(fileobj=reader, mode="r|") as tf:
                # Just iterate through members to validate
                for _ in tf:
                    pass
        return True
    except Exception as e:
        logger.debug("Tar.zstd validation failed for %s: %s", path, e)
        return False


def _check_tar_with_lz4(path: Path) -> bool:
    """Validate an LZ4-compressed tar file using streaming."""
    try:
        with open(path, "rb") as f:
            decompressor = LZ4FrameDecompressor(f)
            with tarfile.open(fileobj=decompressor, mode="r|") as tf:
                for _ in tf:
                    pass
        return True
    except Exception as e:
        logger.debug("Tar.lz4 validation failed for %s: %s", path, e)
        return False


def _check_tar_with_lzma(path: Path) -> bool:
    """Validate an LZMA-compressed tar file using streaming."""
    try:
        with lzma.open(path, "rb") as f:
            with tarfile.open(fileobj=f, mode="r|") as tf:
                for _ in tf:
                    pass
        return True
    except Exception as e:
        logger.debug("Tar.lzma validation failed for %s: %s", path, e)
        return False


def _brotli_stream_reader(fileobj: BufferedReader):

    class BrotliReader:
        def __init__(self, fh) -> None:
            self.fh = fh
            self.decompressor = brotli.Decompressor()
            self.buf = b""
            self.eof = False

        def read(self, size: int = -1) -> bytes:
            while not self.eof and (size < 0 or len(self.buf) < size):
                chunk = self.fh.read(64 * 1024)
                if not chunk:
                    self.buf += self.decompressor.flush()
                    self.eof = True
                else:
                    self.buf += self.decompressor.process(chunk)
            if size < 0:
                data, self.buf = self.buf, b""
            else:
                data, self.buf = self.buf[:size], self.buf[size:]
            return data

    return BrotliReader(fileobj)


class SnappyError(Exception):
    pass


class CompressionError(SnappyError):
    def __init__(self, message: str, algorithm: (str | None) = None) -> None:
        super().__init__(message)
        self.algorithm = algorithm


def _encode_varint(value: int) -> bytes:
    result = bytearray()
    while value >= 128:
        result.append(value & 127 | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _hash_4_bytes(data: bytes, pos: int) -> int:
    val = data[pos] | data[pos + 1] << 8 | data[pos + 2] << 16 | data[pos + 3] << 24
    return val * 506832829 >> 32 - 14 & _HASH_TABLE_SIZE - 1


def _emit_literal(output: bytearray, data: bytes, start: int, length: int) -> None:
    if length <= 0:
        return
    if length <= 60:
        output.append(length - 1 << 2)
    elif length <= 256:
        output.append(60 << 2)
        output.append(length - 1)
    elif length <= 65536:
        output.append(61 << 2)
        output.append(length - 1 & 255)
        output.append(length - 1 >> 8 & 255)
    elif length <= 16777216:
        output.append(62 << 2)
        output.append(length - 1 & 255)
        output.append(length - 1 >> 8 & 255)
        output.append(length - 1 >> 16 & 255)
    else:
        output.append(63 << 2)
        output.append(length - 1 & 255)
        output.append(length - 1 >> 8 & 255)
        output.append(length - 1 >> 16 & 255)
        output.append(length - 1 >> 24 & 255)
    output.extend(data[start : start + length])


def _emit_copy(output: bytearray, offset: int, length: int) -> None:
    while length > 0:
        if length >= 4 and length <= 11 and offset <= _MAX_OFFSET_1:
            tag = 1 | length - 4 << 2 | offset >> 8 << 5
            output.append(tag)
            output.append(offset & 255)
            return
        if offset <= _MAX_OFFSET_2:
            copy_len = min(length, 64)
            tag = 2 | copy_len - 1 << 2
            output.append(tag)
            output.append(offset & 255)
            output.append(offset >> 8 & 255)
            length -= copy_len
        else:
            copy_len = min(length, 64)
            tag = 3 | copy_len - 1 << 2
            output.append(tag)
            output.append(offset & 255)
            output.append(offset >> 8 & 255)
            output.append(offset >> 16 & 255)
            output.append(offset >> 24 & 255)
            length -= copy_len


def compress(data: bytes) -> bytes:
    if not data:
        return _encode_varint(0)
    data_len = len(data)
    output = bytearray()
    output.extend(_encode_varint(data_len))
    if data_len < 4:
        _emit_literal(output, data, 0, data_len)
        return bytes(output)
    hash_table = [0] * _HASH_TABLE_SIZE
    pos = 0
    literal_start = 0
    while pos <= data_len - 4:
        h = _hash_4_bytes(data, pos)
        candidate = hash_table[h]
        hash_table[h] = pos
        if (
            (candidate > 0 or (candidate == 0 and pos > 0))
            and pos - candidate <= _MAX_OFFSET_2
            and data[candidate : candidate + 4] == data[pos : pos + 4]
        ):
            if pos > literal_start:
                _emit_literal(output, data, literal_start, pos - literal_start)
            offset = pos - candidate
            match_len = 4
            max_match = min(data_len - pos, 64)
            while match_len < max_match and data[candidate + match_len] == data[pos + match_len]:
                match_len += 1
            _emit_copy(output, offset, match_len)
            pos += match_len
            literal_start = pos
            if pos <= data_len - 4:
                hash_table[_hash_4_bytes(data, pos - 1)] = pos - 1
        else:
            pos += 1
    if literal_start < data_len:
        _emit_literal(output, data, literal_start, data_len - literal_start)
    return bytes(output)


def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            msg = "error length"
            raise CompressionError(msg, algorithm="snappy")
        byte = data[pos]
        pos += 1
        result |= (byte & 127) << shift
        if byte & 128 == 0:
            break
        shift += 7
        if shift > 32:
            msg = "error length"
            raise CompressionError(msg, algorithm="snappy")
    return result, pos


def decompress(data: bytes) -> bytes:
    if not data:
        return b""
    pos = 0
    uncompressed_len, pos = _decode_varint(data, pos)
    output = bytearray(uncompressed_len)
    out_pos = 0
    while pos < len(data) and out_pos < uncompressed_len:
        tag = data[pos]
        pos += 1
        element_type = tag & 3
        if element_type == 0:
            length = (tag >> 2) + 1
            if length <= 60:
                pass
            else:
                extra_bytes = length - 60
                if pos + extra_bytes > len(data):
                    msg = "error length"
                    raise CompressionError(msg, algorithm="snappy")
                length = 1
                for i in range(extra_bytes):
                    length += data[pos + i] << i * 8
                pos += extra_bytes
            if pos + length > len(data):
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            if out_pos + length > uncompressed_len:
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            output[out_pos : out_pos + length] = data[pos : pos + length]
            pos += length
            out_pos += length
        elif element_type == 1:
            length = (tag >> 2 & 7) + 4
            if pos >= len(data):
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            offset = tag >> 5 << 8 | data[pos]
            pos += 1
            if offset == 0:
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            if offset > out_pos:
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            if out_pos + length > uncompressed_len:
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            for i in range(length):
                output[out_pos + i] = output[out_pos - offset + i]
            out_pos += length
        elif element_type == 2:
            length = (tag >> 2) + 1
            if pos + 2 > len(data):
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            offset = data[pos] | data[pos + 1] << 8
            pos += 2
            if offset == 0:
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            if offset > out_pos:
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            if out_pos + length > uncompressed_len:
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            for i in range(length):
                output[out_pos + i] = output[out_pos - offset + i]
            out_pos += length
        else:
            length = (tag >> 2) + 1
            if pos + 4 > len(data):
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            offset = data[pos] | data[pos + 1] << 8 | data[pos + 2] << 16 | data[pos + 3] << 24
            pos += 4
            if offset == 0:
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            if offset > out_pos:
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            if out_pos + length > uncompressed_len:
                msg = "error length"
                raise CompressionError(msg, algorithm="snappy")
            for i in range(length):
                output[out_pos + i] = output[out_pos - offset + i]
            out_pos += length
    if out_pos != uncompressed_len:
        msg = "error length"
        raise CompressionError(msg, algorithm="snappy")
    return bytes(output)


def xtar(path: str, xpath: str | None = None, preserve_permissions: bool = True) -> bool:
    path = Path(path)
    try:
        if xpath is None:
            xpath = path.stem
        xpath.mkdir(exist_ok=True)
        if path.endswith(".tar.zst"):
            import zstandard as zstd

            with open(path, "rb") as compressed_file:
                dctx = zstd.ZstdDecompressor()
                with dctx.stream_reader(compressed_file) as reader:
                    with tarfile.open(fileobj=reader, mode="r|") as tar:
                        tar.extractall(path=xpath, set_attrs=preserve_permissions, filter="data")
        else:
            mode = None
            if path.endswith((".tar.gz", ".tgz")):
                mode = "r:gz"
            elif path.endswith((".tar.bz2", ".tbz2")):
                mode = "r:bz2"
            elif path.endswith(".tar.xz"):
                mode = "r:xz"
            elif path.endswith(".tar"):
                mode = "r"
            else:
                with tarfile.open(path, "r:*") as tar:
                    tar.extractall(path=xpath, set_attrs=preserve_permissions)
                return True
            with tarfile.open(path, mode) as tar:
                tar.extractall(path=xpath, set_attrs=preserve_permissions)
        return True
    except ImportError as e:
        if "zstandard" in str(e):
            print("Error: 'zstandard' package is required for .tar.zst files.")
            print("Install with: pip install zstandard")
        else:
            print(f"Import error: {e}")
        return False
    except Exception as e:
        print(f"Extraction failed: {e}")
        return False


def _zstd_stream_reader(fileobj: BufferedReader, threads: int = 0) -> ZstdDecompressionReader:
    import zstandard as zstd

    dctx = zstd.ZstdDecompressor()
    return dctx.stream_reader(fileobj, read_size=1024 * 1024, read_across_frames=True, threads=threads)


def _lz4_stream_reader(fileobj: BufferedReader) -> LZ4FrameDecompressor:
    """Streaming decompressor for LZ4 frame format (standard .lz4)."""

    return lz4.frame.LZ4FrameDecompressor(fileobj)


_TAR_SUFFIXES = [
    (".tar", ".gz"),
    (".tar", ".bz2"),
    (".tar", ".xz"),
    (".tar", ".zst"),
    (".tar", ".br"),
    (".tar", ".lzma"),
    (".tar", ".lz4"),
    (".tar", ".zip"),
    (".tar", ".7z"),
    (".tar",),
]


def _is_tar_archive(suffixes: tuple[str, ...]) -> bool:
    """True if suffixes match any of the known tarball extension patterns."""
    return any(suffixes[-len(pat) :] == pat for pat in _TAR_SUFFIXES if len(pat) <= len(suffixes))


def _strip_tar_suffix(name: str, suffixes: tuple[str, ...]) -> str:
    """Remove the tar‑related suffixes from a file name."""
    for pat in _TAR_SUFFIXES:
        if len(pat) <= len(suffixes) and suffixes[-len(pat) :] == pat:
            suffix_str = "".join(pat)
            if name.endswith(suffix_str):
                return name[: -len(suffix_str)]
    msg = f"Unexpected tar suffix pattern: {suffixes}"
    raise ValueError(msg)


_SIMPLE_COMP = {".gz", ".bz2", ".xz", ".lzma", ".br", ".zst", ".lz4"}
_ARCHIVE = {".zip", ".7z", ".whl", ".deb", ".rpm"}


def _unique_path(directory: Path, stem: str, is_dir: bool) -> Path:
    """Return a free path by appending '_1', '_2', … to `stem`."""
    cnt = 1
    while True:
        new_name = f"{stem}_{cnt}"
        candidate = directory / new_name
        if not candidate.exists():
            return candidate
        cnt += 1


def extract_archive(archive_path: str, extract_dir: str | None = None) -> dict:
    """
    Auto-extract a compressed archive based on its extension.

    Parameters
    ----------
    archive_path : str
        Path to the archive file.
    extract_dir : str, optional
        Directory where the content will be extracted.
        Defaults to the current working directory.

    Returns:
    -------
    dict
        Keys: 'status' ('ok','skip','failed'), 'path', 'decomp_path',
              'orig_size', 'decomp_size'.
    """
    archive = Path(archive_path).resolve()
    if not archive.is_file():
        return {
            "status": "failed",
            "path": str(archive),
            "decomp_path": None,
            "orig_size": 0,
            "decomp_size": 0,
        }

    dest_dir = Path(extract_dir).resolve() if extract_dir else Path.cwd()
    orig_size = archive.stat().st_size

    suffixes = archive.suffixes
    is_tar = _is_tar_archive(suffixes)
    if is_tar:
        base_name = _strip_tar_suffix(archive.name, suffixes)
        target_type = "dir"
    elif suffixes[-1] in _SIMPLE_COMP:
        base_name = archive.stem
        target_type = "file"
    elif suffixes[-1] in _ARCHIVE:
        base_name = archive.stem
        target_type = "dir"
    else:
        logger.warning("Unsupported extension: %s", suffixes)
        return {
            "status": "failed",
            "path": str(archive),
            "decomp_path": None,
            "orig_size": orig_size,
            "decomp_size": 0,
        }

    final_target = dest_dir / base_name
    if not is_tar and final_target.exists():
        final_target = _unique_path(dest_dir, base_name, target_type == "dir")
    if is_tar and final_target.exists():
        logger.info("Target %s already exists; skipping tar extraction.", final_target)
        return {
            "status": "skip",
            "path": str(archive),
            "decomp_path": str(final_target),
            "orig_size": orig_size,
            "decomp_size": 0,
        }

    tmp_dir = Path(tempfile.mkdtemp(prefix="extract_"))

    try:
        if is_tar:
            decomp_size = _extract_tar(archive, suffixes, tmp_dir)
        elif suffixes[-1] in _SIMPLE_COMP:
            tmp_file = tmp_dir / base_name
            decomp_size = _extract_single_compressed(archive, suffixes[-1], tmp_file)
        else:
            decomp_size = _extract_archive(archive, suffixes[-1], tmp_dir)

        if decomp_size == 0:
            logger.info("Decompressed size is 0; skipping.")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {
                "status": "skip",
                "path": str(archive),
                "decomp_path": str(final_target),
                "orig_size": orig_size,
                "decomp_size": 0,
            }

        if target_type == "dir":
            contents = list(tmp_dir.iterdir())
            if len(contents) == 1 and contents[0].is_dir():
                src = contents[0]
            else:
                src = tmp_dir
                shutil.rmtree(final_target, ignore_errors=True)
                shutil.move(str(tmp_dir), str(final_target))
                src = final_target
                tmp_dir = None
        else:
            src = tmp_dir / base_name
            final_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(final_target))

        if target_type == "dir" and tmp_dir is not None:
            final_target.parent.mkdir(parents=True, exist_ok=True)
            if src != tmp_dir:
                shutil.move(str(src), str(final_target))
            shutil.rmtree(tmp_dir, ignore_errors=True)

        archive.unlink()
        logger.info("Successfully extracted %s to %s", archive, final_target)
        return {
            "status": "ok",
            "path": str(archive),
            "decomp_path": str(final_target),
            "orig_size": orig_size,
            "decomp_size": decomp_size,
        }

    except Exception:
        logger.exception("Extraction failed for %s", archive)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {
            "status": "failed",
            "path": str(archive),
            "decomp_path": None,
            "orig_size": orig_size,
            "decomp_size": 0,
        }


def _extract_tar(archive_path: Path, suffixes: tuple[str, ...], dest_dir: Path) -> int:
    """
    Extract a tarball (possibly compressed) into `dest_dir`.
    Returns total uncompressed size (sum of regular file sizes).
    """
    if suffixes[-2:] == (".tar", ".zip"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = zf.namelist()
            tar_member = next(n for n in names if n.endswith(".tar"))
            tmp_tar = dest_dir / tar_member
            zf.extract(tar_member, path=dest_dir)
        archive_path = tmp_tar

    elif suffixes[-2:] == (".tar", ".7z"):
        import py7zr

        with py7zr.SevenZipFile(archive_path, "r") as szf:
            names = szf.getnames()
            tar_member = next(n for n in names if n.endswith(".tar"))
            tmp_tar = dest_dir / tar_member
            szf.extract(targets=[tar_member], path=dest_dir)
        archive_path = tmp_tar

    if suffixes[-1] in (".gz", ".bz2", ".xz", ""):
        mode = {"": "r", ".gz": "r:gz", ".bz2": "r:bz2", ".xz": "r:xz"}.get(suffixes[-1], "r")
        with tarfile.open(archive_path, mode) as tf:
            tf.extractall(path=dest_dir)
            total_size = sum(m.size for m in tf.getmembers() if m.isreg())
    else:
        with open(archive_path, "rb") as fh:
            if suffixes[-1] == ".zst":
                reader = _zstd_stream_reader(fh, threads=4)
            elif suffixes[-1] == ".br":
                reader = _brotli_stream_reader(fh)
            elif suffixes[-1] == ".lzma":
                reader = lzma.LZMAFile(fh, "rb")
            elif suffixes[-1] == ".lz4":
                reader = _lz4_stream_reader(fh)
            else:
                msg = f"Unsupported compression: {suffixes[-1]}"
                raise RuntimeError(msg)

            with tarfile.open(fileobj=reader, mode="r|") as tf:
                tf.extractall(path=dest_dir)
                total_size = 0
                for root, dirs, files in os.walk(dest_dir):
                    for f in files:
                        total_size += Path(os.path.join(root, f)).stat().st_size

    return total_size


def _extract_single_compressed(archive_path: Path, ext: str, dest_file: Path) -> int:
    """Decompress a simple single‑file compressed archive into `dest_file`."""
    decompressor_map = {
        ".gz": lambda fh: gzip.GzipFile(fileobj=fh, mode="rb"),
        ".bz2": lambda fh: bz2.BZ2File(fh, "rb"),
        ".xz": lambda fh: lzma.LZMAFile(fh, "rb"),
        ".lzma": lambda fh: lzma.LZMAFile(fh, "rb"),
        ".zst": lambda fh: _zstd_stream_reader(fh, threads=4),
        ".br": lambda fh: _brotli_stream_reader(fh),
        ".lz4": lambda fh: _lz4_stream_reader(fh),
    }
    opener = decompressor_map.get(ext)
    if opener is None:
        msg = f"Unsupported compression: {ext}"
        raise RuntimeError(msg)

    total = 0
    with open(archive_path, "rb") as fin, open(dest_file, "wb") as fout:
        dec = opener(fin)
        while True:
            chunk = dec.read(1024 * 1024)
            if not chunk:
                break
            fout.write(chunk)
            total += len(chunk)
    return total


def _extract_archive(archive_path: Path, ext: str, dest_dir: Path) -> int:
    """Extract a multi‑file archive (.zip, .7z, .whl, .deb, .rpm) into dest_dir."""
    total = 0
    if ext in (".zip", ".whl"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(path=dest_dir)
            total = sum(info.file_size for info in zf.infolist())
    elif ext == ".7z":
        import py7zr

        with py7zr.SevenZipFile(archive_path, "r") as szf:
            szf.extractall(path=dest_dir)
            total = szf.archiveinfo().uncompressed_size
    elif ext == ".deb":
        total = _extract_deb(archive_path, dest_dir)
    elif ext == ".rpm":
        total = _extract_rpm(archive_path, dest_dir)
    else:
        msg = f"Unsupported archive: {ext}"
        raise RuntimeError(msg)
    return total


def _extract_deb(deb_path: Path, dest_dir: Path) -> int:
    """Extract a .deb package using python‑arfile or fallback to subprocess."""
    try:
        import arfile
    except ImportError:
        return _extract_deb_subprocess(deb_path, dest_dir)

    with open(deb_path, "rb") as f:
        ar = arfile.ArFile(f)
        data_member = None
        for member in ar:
            if member.name.startswith("data.tar"):
                data_member = member
                break
        if data_member is None:
            msg = "No data.tar found in .deb"
            raise RuntimeError(msg)
        data = ar.open(data_member)
        name = data_member.name
        if name.endswith(".tar.xz"):
            opener = lzma.LZMAFile
        elif name.endswith(".tar.gz"):
            opener = gzip.GzipFile
        elif name.endswith(".tar.bz2"):
            opener = bz2.BZ2File
        elif name.endswith(".tar"):

            def opener(fh):
                return fh

        else:
            msg = f"Unknown data archive: {name}"
            raise RuntimeError(msg)
        with (
            opener(data) as tarstream,
            tarfile.open(fileobj=tarstream, mode="r|") as tf,
        ):
            tf.extractall(path=dest_dir)
            total = sum(m.size for m in tf.getmembers() if m.isreg())
    return total


def _extract_deb_subprocess(deb_path: Path, dest_dir: Path) -> int:
    """Extract .deb using `ar` and `tar` commands."""

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        subprocess.run(["ar", "x", str(deb_path)], cwd=tmp_dir, check=True)
        tar_files = list(tmp_dir.glob("data.tar.*"))
        if not tar_files:
            msg = "data.tar.* not found in .deb"
            raise RuntimeError(msg)
        subprocess.run(["tar", "-xf", str(tar_files[0]), "-C", str(dest_dir)], check=True)
        total = 0
        for root, dirs, files in os.walk(dest_dir):
            for f in files:
                total += Path(os.path.join(root, f)).stat().st_size
        return total
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _extract_rpm(rpm_path: Path, dest_dir: Path) -> int:
    """Extract an .rpm package using python‑rpmfile or subprocess."""
    try:
        import rpmfile
    except ImportError:
        return _extract_rpm_subprocess(rpm_path, dest_dir)

    with open(rpm_path, "rb") as f:
        rpm = rpmfile.RPMFile(f)
        payload = rpm.payload_stream
        return _extract_rpm_subprocess(rpm_path, dest_dir)


def _extract_rpm_subprocess(rpm_path: Path, dest_dir: Path) -> int:
    """Extract .rpm using rpm2cpio and cpio."""

    cmd = f"rpm2cpio '{rpm_path}' | (cd '{dest_dir}' && cpio -idm --quiet)"
    subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")
    total = 0
    for root, dirs, files in os.walk(dest_dir):
        for f in files:
            total += Path(os.path.join(root, f)).stat().st_size
    return total
