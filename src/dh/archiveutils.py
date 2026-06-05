from __future__ import annotations
from pathlib import Path
import zipfile
import tarfile

_HASH_TABLE_SIZE = 1 << 14
_MAX_OFFSET_1 = 2047
_MAX_OFFSET_2 = 65535
import zipfile


def is_wheel_ok(path):
    try:
        with zipfile.ZipFile(path, "r") as wheel:
            corrupt_file = wheel.testzip()
            if corrupt_file:
                return False
            return True
    except zipfile.BadZipFile:
        return False
    except FileNotFoundError:
        return False
    except Exception as e:
        return False


def is_valid_archive(path: str | Path) -> bool:
    path = Path(path)
    try:
        if not path.is_file():
            return False
        if not path.stat().st_size:
            return False
        lower = path.name.lower()
        if lower.endswith(".zip") or lower.endswith(".whl"):
            return is_wheel_ok(path)
        if lower.endswith(".tar"):
            return _check_tar(path, mode="r:")
        if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
            return _check_tar(path, mode="r:gz")
        if lower.endswith(".tar.xz") or lower.endswith(".txz"):
            return _check_tar(path, mode="r:xz")
        if lower.endswith(".tar.bz2") or lower.endswith(".tbz2") or lower.endswith(".tbz"):
            return _check_tar(path, mode="r:bz2")
        if lower.endswith(".tar.br"):
            return _check_tar_with_brotli(path)
        if lower.endswith(".tar.zst"):
            return _check_tar_with_zstd(path)
        if lower.endswith(".tar.lz4"):
            return _check_tar_with_lz4(path)
        if lower.endswith(".tar.lzma"):
            return _check_tar_with_lzma(path)
        if lower.endswith(".br"):
            return _check_brotli_file(path)
        if lower.endswith(".zst"):
            return _check_zstd_file(path)
        if lower.endswith(".lz4"):
            return _check_lz4_file(path)
        if lower.endswith(".lzma"):
            return _check_lzma_file(path)
        return False
    except Exception:
        return False


def _check_tar(path: str | Path, mode: str) -> bool:
    path = Path(path)
    with tarfile.open(path, mode) as tf:
        bad = tf.badfile()
        if bad is not None:
            return False
        tf.getmembers()
        return True


def _check_brotli_file(path: str | Path) -> bool:
    from brotlicffi import decompress as brotli_decompress

    path = Path(path)
    try:
        with open(path, "rb") as f:
            data = f.read()
        _ = brotli_decompress(data)
        return True
    except:
        return False


def _check_zstd_file(path: str | Path) -> bool:
    from zstandard import ZstdDecompressor as zstd_ZstdDecompressor

    path = Path(path)
    try:
        dctx = zstd_ZstdDecompressor()
        with open(path, "rb") as f:
            _ = dctx.decompress(f.read())
        return True
    except:
        return False


def _check_lz4_file(path: str | Path) -> bool:
    from lz4.frame import decompress as lz4_decompress

    path = Path(path)
    try:
        with open(path, "rb") as f:
            _ = lz4_decompress(f.read())
        return True
    except:
        return False


def _check_lzma_file(path: str | Path) -> bool:
    from lzma import decompress as lzma_decompress

    path = Path(path)
    try:
        with open(path, "rb") as f:
            _ = lzma_decompress(f.read())
        return True
    except:
        return False


def _check_tar_with_brotli(path: str | Path) -> bool:
    from brotlicffi import decompress as brotli_decompress

    path = Path(path)
    try:
        with open(path, "rb") as f:
            raw = brotli_decompress(f.read())
        return _check_tar_bytes(raw)
    except:
        return False


def _check_tar_with_zstd(path: str | Path) -> bool:
    path = Path(path).resolve()
    extract_path = path.with_name(path.name.replace(".tar.zst", ""))
    try:
        with tarfile.open(path, "r:zst") as f:
            f.extractall(path=extract_path, filter="data")
        return True
    except:
        return False


def _check_tar_with_lz4(path: str | Path) -> bool:
    from lz4.frame import decompress as lz4_decompress

    path = Path(path)
    try:
        with open(path, "rb") as f:
            raw = lz4_decompress(f.read())
        return _check_tar_bytes(raw)
    except:
        return False


def _check_tar_with_lzma(path: str | Path) -> bool:
    from lzma import decompress as lzma_decompress

    path = Path(path)
    try:
        with open(path, "rb") as f:
            raw = lzma_decompress(f.read())
        return _check_tar_bytes(raw)
    except:
        return False


def _check_tar_bytes(raw: bytes) -> bool:
    from io import BytesIO as io_BytesIO

    try:
        with tarfile.open(fileobj=io_BytesIO(raw), mode="r:") as tf:
            tf.getmembers()
        return True
    except:
        return False


class SnappyError(Exception):
    pass


class CompressionError(SnappyError):
    def __init__(self, message: str, algorithm: str | None = None):
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
        if length >= 4 and length <= 11 and (offset <= _MAX_OFFSET_1):
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
            and (data[candidate : candidate + 4] == data[pos : pos + 4])
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
    return (result, pos)


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
