from _typeshed import Incomplete

from __future__ import annotations
import ipaddress
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse


def slugify(string: Incomplete) -> str: ...


def get_sha256(path: str | Path, chunk_size: int = 524288) -> str: ...


def has_doc(code: str) -> bool: ...


def is_valid_url(url: str) -> bool: ...


def is_valid_hostname(hostname: str) -> bool: ...


pattern: Pattern[str]
