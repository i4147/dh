from pathlib import Path
from chardet import detect
from dh import BIN_EXT


def detect2(data: bytes) -> dict:
    try:
        data.decode("utf-8")
        return {"encoding": "utf-8", "confidence": 0.99}
    except UnicodeDecodeError:
        try:
            data.decode("latin-1")
            return {"encoding": "latin-1", "confidence": 0.7}
        except UnicodeDecodeError:
            return {"encoding": None, "confidence": 0.1}


TEXT_CHARS = bytes(range(32, 127)) + b"\n\r\t\f\b"


def is_likely_binary_chunk(chunk: bytes, threshold: float = 0.30) -> bool:
    if not chunk:
        return False
    if b"\x00" in chunk:
        return True
    non_text_count = 0
    for byte in chunk:
        if bytes([byte]) not in TEXT_CHARS:
            non_text_count += 1
    non_text_ratio = non_text_count / len(chunk)
    return non_text_ratio > threshold


def is_text_file(
    path: str | Path,
    chunk_size: int = 32678,
    encoding_confidence_threshold: float = 0.95,
) -> bool:
    path = Path(path)
    ext = path.suffix.lower()
    if ext in BIN_EXT:
        return False
    try:
        with path.open("rb") as f:
            chunk = f.read(chunk_size)
            if not chunk:
                return True
            if is_likely_binary_chunk(chunk, threshold=0.30):
                return False
            detected_encoding = detect(chunk)
            if detected_encoding and detected_encoding["confidence"] >= encoding_confidence_threshold:
                if detected_encoding["encoding"] != "ascii":
                    return True
                else:
                    return True
            else:
                return True
    except Exception as e:
        print(f"Error processing file {path}: {e}")
        return False


if __name__ == "__main__":
    Path("sample.txt").write_text("This is a plain text file.\nIt contains UTF-8 characters like: é, ü, ñ.\n")
    Path("sample.bin").write_bytes(b"\x01\x02\x03\x00" + b"binary data" * 50)
    Path("sample.empty").write_bytes(b"")
    Path("sample.ascii").write_text("This is pure ASCII text.")
    Path("sample.iso8859").write_text("This has Latin-1 chars: \xe9\xfc\xf1")
    print(f"'sample.txt' is text: {is_text_file(Path('sample.txt'))}")
    print(f"'sample.bin' is text: {is_text_file(Path('sample.bin'))}")
    print(f"'sample.empty' is text: {is_text_file(Path('sample.empty'))}")
    print(f"'sample.ascii' is text: {is_text_file(Path('sample.ascii'))}")
    print(f"'sample.iso8859' is text: {is_text_file(Path('sample.iso8859'))}")
    Path("sample.txt").unlink()
    Path("sample.bin").unlink()
    Path("sample.empty").unlink()
    Path("sample.ascii").unlink()
    Path("sample.iso8859").unlink()
