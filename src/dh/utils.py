from __future__ import annotations

import ast
import ipaddress
import re
import tokenize
import unicodedata
from collections.abc import Iterator
from hashlib import sha256
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse

pattern: re.Pattern[str] = re.compile(
    r"""(?:
            url\s*\(\s*["']?
          | (?:src|href)\s*=\s*["']
        )
        data:([^;,]+)
        (?:;[^,]*)?
        ;base64,\s*
        ([A-Za-z0-9+/]+={0,2})
        ["']?
        (?:\s*\))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

WORD_PATTERN: re.Pattern[str] = re.compile(
    r"""
    [A-Z]+(?=[A-Z][a-z]|\d|\b)   # Acronym followed by lowercase or number
    |[A-Z]?[a-z]+                # Standard word
    |[A-Z]+                      # All caps word
    |\d+                         # Numbers (optional)
    """,
    re.VERBOSE,
)

_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_HOSTNAME_LABEL_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$")


def get_sha256(path: str | Path, chunk_size: int = 524288) -> str:
    """Return the hex-encoded SHA-256 digest of the file at *path*.

    The file is read in chunks of *chunk_size* bytes to keep memory usage
    bounded regardless of the file size.
    """
    path = Path(path)
    h = sha256()

    def _chunks() -> Iterator[bytes]:
        with path.open("rb") as f:
            yield from iter(lambda: f.read(chunk_size), b"")

    for chunk in _chunks():
        h.update(chunk)
    return h.hexdigest()


def has_doc(code: str) -> bool:
    """Return True if *code* contains a comment or a docstring.

    Comments are detected with the ``tokenize`` module; docstrings are
    detected by parsing the source with ``ast`` and looking for a
    non-``None`` docstring on the module, a function, an async function,
    or a class.
    """
    try:
        tokens: Iterator[tokenize.TokenInfo] = tokenize.generate_tokens(StringIO(code).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                return True
    except Exception:
        pass

    try:
        tree: ast.Module = ast.parse(code)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if (
            isinstance(
                node,
                (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            )
            and ast.get_docstring(node) is not None
        ):
            return True
    return False


def _is_valid_hostname(hostname: str) -> bool:
    """Return True if *hostname* is a syntactically valid hostname.

    Accepts ``localhost``, IPv4, IPv6, and DNS hostnames per RFC 1123.
    """
    if hostname == "localhost":
        return True

    try:
        ipaddress.IPv4Address(hostname)
        return True
    except ValueError:
        pass

    try:
        ipaddress.IPv6Address(hostname)
        return True
    except ValueError:
        pass

    if len(hostname) > 253:
        return False

    labels: list[str] = hostname.split(".")
    if not labels:
        return False

    for label in labels:
        if not label or len(label) > 63:
            return False
        if not _HOSTNAME_LABEL_PATTERN.match(label):
            return False
    return True


def is_valid_url(url: str) -> bool:
    """Return True if *url* is a syntactically valid absolute URL.

    Only ``http``, ``https``, ``ftp``, and ``ftps`` schemes are accepted.
    URLs containing template placeholders (``${...}``) or backticks are
    rejected.
    """
    if not isinstance(url, str) or not url.strip():
        return False

    url = url.strip()
    if "${" in url or "`" in url:
        return False
    if "://" not in url:
        return False

    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https", "ftp", "ftps"):
        return False

    if parsed.port is not None and not (0 < parsed.port < 65536):
        return False

    if not parsed.hostname:
        return False

    hostname: str = parsed.hostname
    return _is_valid_hostname(hostname)


def slugify(string: str) -> str:
    """Return an ASCII, lower-case, hyphen-separated slug of *string*."""
    normalized: str = unicodedata.normalize("NFKD", string).encode("ascii", "ignore").decode("ascii")
    return re.sub(
        r"[-\s]+",
        "-",
        re.sub(r"[^\w\s-]", "", normalized).strip().lower(),
    )


def tokenize_text(text: str) -> list[str]:
    """Split *text* into identifier subword tokens.

    Identifiers are matched with ``[A-Za-z_][A-Za-z0-9_]*`` and then
    further split on camelCase / PascalCase / SCREAMING_CASE boundaries
    and digit sequences using :data:`WORD_PATTERN`.
    """
    tokens: list[str] = []
    for match in _IDENTIFIER_PATTERN.finditer(text):
        identifier: str = match.group()
        subwords: list[str] = WORD_PATTERN.findall(identifier)
        tokens.extend(subwords if subwords else [identifier])
    return tokens
