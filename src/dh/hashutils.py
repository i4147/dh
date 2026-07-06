from pathlib import Path

from .const import CHUNK_SIZE
from .fileutils import runcmd


def get_openssl_hash(path, alg):
    from re import match as re_match

    if not alg.startswith("-"):
        alg = "-" + alg
    cmd = ["openssl", "dgst", "-hex", "-r", alg, str(path)]
    _, output, _ = runcmd(cmd)
    if output is None:
        return ""
    matchz = re_match("^(\\S+) ", output)
    if matchz:
        return matchz.group(1)
    return ""


def content_hash(data: bytes) -> str:
    from hashlib import sha256

    if not isinstance(data, bytes):
        data = data.encode("utf8")
    return sha256(data).hexdigest()


def get_sha256(path: str | Path) -> str:
    from hashlib import sha256

    path = Path(path)
    if not path.exists() or not (size := path.stat().st_size):
        return ""
    h = sha256()
    try:
        with path.open("rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, IOError):
        return ""
