from typing import Literal

from __future__ import annotations
import csv
import logging
import math
import os
from pathlib import Path

logger: Logger
BINARY_EXTENSIONS: frozenset[str]
CHUNK_SIZE: Literal[512] = 512


def has_binary_extension(filename: str | bytes | Path) -> bool: ...


def get_starting_chunk(filename: str | bytes | Path, length: int = ...) -> bytes: ...


def is_binary_string(bytes_to_check: bytes) -> bool: ...


def is_binary(filename: str | bytes | Path, *, check_extensions: bool = True) -> bool: ...
