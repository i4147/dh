from __future__ import annotations

import logging
import math
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)
__all__ = [
    "BINARY_EXTENSIONS",
    "BINARY_SIGNATURES",
    "CHUNK_SIZE",
    "get_starting_chunk",
    "has_binary_extension",
    "is_binary",
    "is_binary_string",
]
BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        "3ds",
        "blend",
        "dae",
        "fbx",
        "glb",
        "stl",
        "usdz",
        "7z",
        "bz2",
        "cab",
        "gz",
        "jar",
        "lz",
        "lz4",
        "lzma",
        "rar",
        "tar",
        "xz",
        "z",
        "zip",
        "zst",
        "aac",
        "aif",
        "aiff",
        "alac",
        "ape",
        "flac",
        "m4a",
        "mid",
        "midi",
        "mp3",
        "ogg",
        "opus",
        "wav",
        "wma",
        "dwg",
        "dwf",
        "dxb",
        "step",
        "stp",
        "class",
        "dll",
        "o",
        "pyc",
        "pyo",
        "so",
        "wasm",
        "accdb",
        "db",
        "dbf",
        "mdb",
        "sqlite",
        "sqlite3",
        "dmg",
        "img",
        "iso",
        "qcow2",
        "vdi",
        "vhd",
        "vmdk",
        "doc",
        "docx",
        "epub",
        "mobi",
        "odt",
        "pages",
        "pdf",
        "ppt",
        "pptx",
        "xls",
        "xlsx",
        "com",
        "exe",
        "msi",
        "bin",
        "fw",
        "rom",
        "eot",
        "otf",
        "ttc",
        "ttf",
        "woff",
        "woff2",
        "gba",
        "n64",
        "nds",
        "nes",
        "pak",
        "sav",
        "sfc",
        "smc",
        "shp",
        "shx",
        "avif",
        "bmp",
        "cr2",
        "cr3",
        "dng",
        "gif",
        "heic",
        "heif",
        "ico",
        "jfif",
        "jp2",
        "jpeg",
        "jpg",
        "jxl",
        "nef",
        "orf",
        "png",
        "psd",
        "raw",
        "tif",
        "tiff",
        "webp",
        "xcf",
        "arrow",
        "avro",
        "fit",
        "fits",
        "hdf5",
        "mat",
        "npy",
        "npz",
        "parquet",
        "pcap",
        "pcapng",
        "avi",
        "flv",
        "m4v",
        "mkv",
        "mov",
        "mp4",
        "mpeg",
        "mpg",
        "ogv",
        "webm",
        "wmv",
    }
)
BINARY_SIGNATURES: tuple[bytes, ...] = tuple(
    sorted(
        (
            bytes.fromhex(h)
            for h in (
                "89504e470d0a1a0a",
                "ffd8ffe0",
                "ffd8ffe1",
                "474946383761",
                "474946383961",
                "424d",
                "4d4d002a",
                "49492a00",
                "00000100",
                "255044462d312e",
                "53514c69746520666f726d6174203300",
                "504b0304",
                "1f8b08",
                "fd377a585a00",
                "7f454c46",
                "feedface",
                "cefaedfe",
                "feedfacf",
                "cffaedfe",
                "4d5a",
                "cafebabe",
                "52494646",
                "4f676753",
                "664c6143",
                "0061736d",
                "774f4646",
                "4f54544f",
                "0001000000",
                "0000000142756431",
                "774f4632",
                "524946460000000057454250",
                "0000001866747970",
                "494433",
                "425a68",
                "377abcaf271c",
                "d0cf11e0a1b11ae1",
                "28b52ffd",
                "526172211a07",
                "1a45dfa3",
                "4d546864",
                "38425053",
                "0000001c6674797068656963",
                "50415231",
                "6465780a",
                "4243c0de",
                "5041434b",
                "62706c697374",
                "213c617263683e0a",
                "04224d18",
                "4152524f5731",
                "4f626a01",
                "5d0000",
                "a1b2c3d4",
                "ff060000734e61507059",
                "feedfeed",
                "303730373031",
            )
        ),
        key=len,
        reverse=True,
    )
)
CHUNK_SIZE = 512
_CONTROL_BYTES: frozenset[int] = frozenset(range(32)) - {9, 10, 13}


def _has_known_binary_signature(chunk: bytes) -> bool:
    for sig in BINARY_SIGNATURES:
        if chunk.startswith(sig):
            return True
    return False


def has_binary_extension(filename: str | bytes | Path) -> bool:
    if isinstance(filename, bytes):
        filename = os.fsdecode(filename)
    name = str(filename)
    dot = name.rfind(".")
    if dot < 0 or dot == len(name) - 1:
        return False
    slash = max(name.rfind("/"), name.rfind(os.sep))
    if dot < slash:
        return False
    return name[dot + 1 :].lower() in BINARY_EXTENSIONS


def get_starting_chunk(filename: str | bytes | Path, length: int = CHUNK_SIZE) -> bytes:
    with open(filename, "rb") as f:
        return f.read(length)


_DECODE_TRY = (
    "utf-16-le",
    "utf-16-be",
    "utf-32-le",
    "utf-32-be",
    "gb2312",
    "big5",
    "shift_jis",
    "euc-jp",
    "euc-kr",
)


def _try_decode(chunk: bytes, encoding: str) -> float:
    try:
        chunk.decode(encoding)
        return 1.0
    except (UnicodeDecodeError, ValueError, LookupError):
        return 0.0


def _compute_features(chunk: bytes) -> list[float]:
    n = len(chunk)
    if n == 0:
        return [0.0] * 24
    null_count = 0
    control_count = 0
    printable_count = 0
    high_count = 0
    hist = [0] * 256
    max_run = current_run = 0
    for b in chunk:
        hist[b] += 1
        if b == 0:
            null_count += 1
        elif b in _CONTROL_BYTES:
            control_count += 1
        elif 0x20 <= b <= 0x7E:
            printable_count += 1
        elif b >= 0x80:
            high_count += 1
        if 0x20 <= b <= 0x7E or b == 9 or b == 10 or b == 13:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    inv_n = 1.0 / n
    null_ratio = null_count * inv_n
    control_ratio = control_count * inv_n
    printable_ascii_ratio = printable_count * inv_n
    high_byte_ratio = high_count * inv_n
    try:
        chunk.decode("utf-8")
        utf8_valid = 1.0
    except (UnicodeDecodeError, ValueError):
        utf8_valid = 0.0
    even_total = (n + 1) // 2
    odd_total = n // 2
    even_nulls = 0
    odd_nulls = 0
    even_nulls = chunk[0::2].count(0)
    odd_nulls = chunk[1::2].count(0)
    even_null_ratio = even_nulls / even_total if even_total else 0.0
    odd_null_ratio = odd_nulls / odd_total if odd_total else 0.0
    entropy = 0.0
    for count in hist:
        if count:
            p = count * inv_n
            entropy -= p * math.log2(p)
    bom_utf32le = 1.0 if chunk[:4] == b"\xff\xfe\x00\x00" else 0.0
    bom_utf32be = 1.0 if chunk[:4] == b"\x00\x00\xfe\xff" else 0.0
    bom_utf16le = 1.0 if chunk[:2] == b"\xff\xfe" and chunk[:4] != b"\xff\xfe\x00\x00" else 0.0
    bom_utf16be = 1.0 if chunk[:2] == b"\xfe\xff" else 0.0
    bom_utf8 = 1.0 if chunk[:3] == b"\xef\xbb\xbf" else 0.0
    if n >= 10:
        try_utf16le = _try_decode(chunk, "utf-16-le")
        try_utf16be = _try_decode(chunk, "utf-16-be")
    else:
        try_utf16le = try_utf16be = 0.0
    if n >= 16:
        try_utf32le = _try_decode(chunk, "utf-32-le")
        try_utf32be = _try_decode(chunk, "utf-32-be")
    else:
        try_utf32le = try_utf32be = 0.0
    longest_printable_run = max_run * inv_n
    if n >= 10:
        try_gb2312 = _try_decode(chunk, "gb2312")
        try_big5 = _try_decode(chunk, "big5")
        try_shift_jis = _try_decode(chunk, "shift_jis")
        try_euc_jp = _try_decode(chunk, "euc-jp")
        try_euc_kr = _try_decode(chunk, "euc-kr")
    else:
        try_gb2312 = try_big5 = try_shift_jis = try_euc_jp = try_euc_kr = 0.0
    has_magic_signature = 1.0 if _has_known_binary_signature(chunk) else 0.0
    return [
        null_ratio,
        control_ratio,
        printable_ascii_ratio,
        high_byte_ratio,
        utf8_valid,
        even_null_ratio,
        odd_null_ratio,
        entropy,
        bom_utf32le,
        bom_utf32be,
        bom_utf16le,
        bom_utf16be,
        bom_utf8,
        try_utf16le,
        try_utf16be,
        try_utf32le,
        try_utf32be,
        longest_printable_run,
        try_gb2312,
        try_big5,
        try_shift_jis,
        try_euc_jp,
        try_euc_kr,
        has_magic_signature,
    ]


def _tree(f: list[float]) -> bool:
    if f[1] <= 0.000977:
        if f[17] <= 0.000977:
            if f[4] <= 0.500000:
                if f[22] <= 0.500000:
                    if f[7] <= 1.953445:
                        return True
                    if f[7] <= 2.749470:
                        return False
                    if f[14] <= 0.500000:
                        return True
                    return True
                return False
            return False
        if f[4] <= 0.500000:
            if f[17] <= 0.063636:
                if f[7] <= 2.021329:
                    return True
                if f[13] <= 0.500000:
                    return False
                return False
            if f[7] <= 3.047898:
                return False
            if f[2] <= 0.758706:
                if f[17] <= 0.134848:
                    if f[3] <= 0.633612:
                        if f[7] <= 3.851786:
                            return False
                        if f[3] <= 0.483333:
                            return False
                        return f[17] <= 0.129167
                    return not f[2] <= 0.145455
                if f[19] <= 0.500000:
                    if f[7] <= 3.572021:
                        if f[3] <= 0.490000:
                            return not f[2] <= 0.651515
                        if f[7] <= 3.370112:
                            return True
                        if f[3] <= 0.651515:
                            if f[17] <= 0.318182:
                                return True
                            return True
                        return True
                    if f[2] <= 0.615079:
                        if f[20] <= 0.500000:
                            if f[13] <= 0.500000:
                                return True
                            return True
                        return not f[17] <= 0.176923
                    return not f[17] <= 0.252381
                return f[7] <= 3.889752
            return False
        return False
    if f[0] <= 0.163978:
        if f[4] <= 0.500000:
            if f[7] <= 3.264621:
                if f[17] <= 0.022678:
                    if f[2] <= 0.000977:
                        return not f[5] <= 0.001953
                    return True
                if f[1] <= 0.095455:
                    if f[17] <= 0.306818:
                        if f[1] <= 0.055728:
                            return False
                        return False
                    return True
                return False
            if f[10] <= 0.500000:
                if f[2] <= 0.455534:
                    if f[3] <= 0.790570:
                        if f[1] <= 0.485714:
                            if f[7] <= 3.540884:
                                if f[7] <= 3.528408:
                                    if f[2] <= 0.316667:
                                        if f[2] <= 0.286364:
                                            if f[17] <= 0.095455:
                                                return True
                                            return True
                                        return not f[13] <= 0.5
                                    return True
                                return False
                            if f[2] <= 0.446657:
                                return True
                            if f[17] <= 0.066638:
                                return not f[2] <= 0.450099
                            return True
                        return False
                    return False
                if f[3] <= 0.425959:
                    if f[3] <= 0.394552:
                        if f[7] <= 4.209417:
                            if f[7] <= 4.175213:
                                if f[3] <= 0.100962:
                                    return False
                                if f[3] <= 0.248047:
                                    return True
                                return not f[17] <= 0.106443
                            return False
                        if f[23] <= 0.500000:
                            return True
                        return True
                    if f[17] <= 0.082906:
                        return False
                    if f[1] <= 0.025000:
                        return False
                    if f[7] <= 3.520764:
                        return False
                    if f[1] <= 0.122500:
                        return True
                    return not f[0] <= 0.033333
                if f[17] <= 0.098599:
                    if f[1] <= 0.012902:
                        return True
                    if f[23] <= 0.500000:
                        return False
                    if f[3] <= 0.458087:
                        return True
                    return True
                if f[7] <= 4.453697:
                    if f[3] <= 0.472136:
                        if f[17] <= 0.121324:
                            return False
                        if f[17] <= 0.302885:
                            return not f[7] <= 3.539612
                        return False
                    return True
                return True
            return False
        if f[1] <= 0.450000:
            return f[1] <= 0.006212
        return True
    if f[23] <= 0.500000:
        if f[3] <= 0.082843:
            if f[6] <= 0.282534:
                return False
            if f[7] <= 3.088801:
                if f[0] <= 0.822852:
                    if f[2] <= 0.291667:
                        return False
                    return not f[1] <= 0.521739
                if f[16] <= 0.500000:
                    return True
                return True
            return not f[5] <= 0.140625
        if f[17] <= 0.291667:
            if f[7] <= 0.698576:
                return True
            if f[7] <= 5.613847:
                if f[2] <= 0.361264:
                    if f[20] <= 0.500000:
                        return False
                    if f[14] <= 0.500000:
                        return not f[0] <= 0.379808
                    return False
                if f[2] <= 0.408333:
                    return not f[1] <= 0.26
                return False
            return not f[17] <= 0.012485
        return True
    if f[20] <= 0.500000:
        return True
    return True


def is_binary_string(bytes_to_check: bytes) -> bool:
    if not bytes_to_check:
        return False
    if _has_known_binary_signature(bytes_to_check):
        return True
    return _tree(_compute_features(bytes_to_check))


def _file_cache_key(filename: str | bytes | Path) -> tuple:
    try:
        st = os.stat(filename)
        return (os.fspath(filename), st.st_mtime_ns, st.st_size)
    except OSError:
        return (os.fspath(filename), None, None)


@lru_cache(maxsize=1024)
def _is_binary_cached(key: tuple, check_extensions: bool) -> bool:
    filename = key[0]
    if check_extensions and has_binary_extension(filename):
        return True
    try:
        chunk = get_starting_chunk(filename)
    except OSError:
        return False
    return is_binary_string(chunk)


def is_binary(filename: str | bytes | Path, *, check_extensions: bool = True) -> bool:
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("is_binary: %r (check_extensions=%r)", filename, check_extensions)
    key = _file_cache_key(filename)
    return _is_binary_cached(key, check_extensions)


def _clear_cache() -> None:
    _is_binary_cached.cache_clear()
