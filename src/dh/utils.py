from pathlib import Path


def is_valid_url(url) -> bool:
    from urllib.parse import urlparse

    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def get_sha256(path: str | Path, chunk_size: int = 524288) -> str:
    from hashlib import sha256

    path = Path(path)
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()
