from pathlib import Path
from .fileutils import runcmd

CHUNK_SIZE = 524288


def get_openssl_hash(path, alg):
    from re import match as re_match

    if not alg.startswith("-"):
        alg = "-" + alg
    cmd = ["openssl", "dgst", "-hex", "-r", alg, str(path)]
    _, output, _ = runcmd(cmd)
    if output is None:
        return ""
    matchz = re_match(r"^(\S+) ", output)
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
    h = sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
                h.update(chunk)
        return h.hexdigest()
    except:
        return ""
