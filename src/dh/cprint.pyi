from typing import Literal

from __future__ import annotations
import os
import sys
from functools import cache
from collections.abc import Iterable
from typing import Any

ATTRIBUTES: dict[str, int]
HIGHLIGHTS: dict[str, int]
COLORS: dict[str, int]
RESET: Literal['[0m'] = "\x1b[0m"


@cache
def can_colorize(*, no_color: bool | None = None, force_color: bool | None = None) -> bool: ...


def colored(text: object, color: str | tuple[int, int, int] | None = None, on_color: str | tuple[int, int, int] | None = None, attrs: Iterable[str] | None = None, *, no_color: bool | None = None, force_color: bool | None = None) -> str: ...


def cprint(text: object, color: str | tuple[int, int, int] | None = None, on_color: str | tuple[int, int, int] | None = None, attrs: Iterable[str] | None = None, *, no_color: bool | None = None, force_color: bool | None = None, **kwargs: Any) -> None: ...


__all__ = ["ATTRIBUTES", "COLORS", "HIGHLIGHTS", "RESET", "can_colorize", "colored", "cprint"]
