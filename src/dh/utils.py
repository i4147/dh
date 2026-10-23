from __future__ import annotations
import ast
from hashlib import sha256
from io import StringIO
from pathlib import Path
import re
import tokenize
from typing import TYPE_CHECKING
import unicodedata
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Iterator
PROTOCOLS = {"http", "https"}
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
    path = Path(path)
    h = sha256()

    def _chunks() -> Iterator[bytes]:
        with path.open("rb") as f:
            yield from iter(lambda: f.read(chunk_size), b"")

    for chunk in _chunks():
        h.update(chunk)
    return h.hexdigest()


def has_doc(code: str) -> bool:
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


def is_valid_url(url: str | None) -> bool:
    try:
        parsed_url = urlsplit(url)
    except ValueError:
        return False
    if not parsed_url.scheme or parsed_url.scheme not in PROTOCOLS:
        return False
    return not (len(parsed_url.netloc) < 5 or (parsed_url.netloc.startswith("www.") and len(parsed_url.netloc) < 8))


def slugify(string: str) -> str:
    normalized: str = unicodedata.normalize("NFKD", string).encode("ascii", "ignore").decode("ascii")
    return re.sub(
        r"[-\s]+",
        "-",
        re.sub(r"[^\w\s-]", "", normalized).strip().lower(),
    )


def tokenize_text(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _IDENTIFIER_PATTERN.finditer(text):
        identifier: str = match.group()
        subwords: list[str] = WORD_PATTERN.findall(identifier)
        tokens.extend(subwords or [identifier])
    return tokens
