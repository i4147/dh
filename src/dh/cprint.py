from __future__ import annotations
from collections.abc import Iterable
from functools import cache
from io import StringIO
import os
import sys
from typing import Any
from rich.console import Console
from rich.style import Style
from rich.text import Text
ATTRIBUTES: dict[str, int] = {
    "bold": 1,
    "dark": 2,
    "italic": 3,
    "underline": 4,
    "blink": 5,
    "reverse": 7,
    "concealed": 8,
    "strike": 9,
}
HIGHLIGHTS: dict[str, int] = {
    "on_black": 40,
    "on_grey": 40,
    "on_red": 41,
    "on_green": 42,
    "on_yellow": 43,
    "on_blue": 44,
    "on_magenta": 45,
    "on_cyan": 46,
    "on_light_grey": 47,
    "on_dark_grey": 100,
    "on_light_red": 101,
    "on_light_green": 102,
    "on_light_yellow": 103,
    "on_light_blue": 104,
    "on_light_magenta": 105,
    "on_light_cyan": 106,
    "on_white": 107,
}
COLORS: dict[str, int] = {
    "black": 30,
    "grey": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "light_grey": 37,
    "dark_grey": 90,
    "light_red": 91,
    "light_green": 92,
    "light_yellow": 93,
    "light_blue": 94,
    "light_magenta": 95,
    "light_cyan": 96,
    "white": 97,
}
RESET = "\x1b[0m"
_RICH_COLORS: dict[str, str] = {
    "black": "black",
    "grey": "black",
    "red": "red",
    "green": "green",
    "yellow": "yellow",
    "blue": "blue",
    "magenta": "magenta",
    "cyan": "cyan",
    "light_grey": "white",
    "dark_grey": "bright_black",
    "light_red": "bright_red",
    "light_green": "bright_green",
    "light_yellow": "bright_yellow",
    "light_blue": "bright_blue",
    "light_magenta": "bright_magenta",
    "light_cyan": "bright_cyan",
    "white": "bright_white",
}
_RICH_HIGHLIGHTS: dict[str, str] = {
    "on_black": "on black",
    "on_grey": "on black",
    "on_red": "on red",
    "on_green": "on green",
    "on_yellow": "on yellow",
    "on_blue": "on blue",
    "on_magenta": "on magenta",
    "on_cyan": "on cyan",
    "on_light_grey": "on white",
    "on_dark_grey": "on bright_black",
    "on_light_red": "on bright_red",
    "on_light_green": "on bright_green",
    "on_light_yellow": "on bright_yellow",
    "on_light_blue": "on bright_blue",
    "on_light_magenta": "on bright_magenta",
    "on_light_cyan": "on bright_cyan",
    "on_white": "on bright_white",
}
_RICH_ATTRIBUTES: dict[str, str] = {
    "bold": "bold",
    "dark": "dim",
    "italic": "italic",
    "underline": "underline",
    "blink": "blink",
    "reverse": "reverse",
    "concealed": "conceal",
    "strike": "strike",
}
ColorSpec = str | tuple[int, int, int]
@cache
def can_colorize(*, no_color: bool | None = None, force_color: bool | None = None) -> bool:
    if no_color is not None and no_color:
        return False
    if force_color is not None and force_color:
        return True
    if os.environ.get("ANSI_COLORS_DISABLED"):
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("TERM") == "dumb":
        return False
    if not hasattr(sys.stdout, "fileno"):
        return False
    try:
        return os.isatty(sys.stdout.fileno())
    except OSError:
        return sys.stdout.isatty()
@cache
def _terminal_color_system() -> str:
    probe = Console(force_terminal=False)
    detected = probe.color_system
    if detected:
        return detected
    return "truecolor"
def _color_token(color: ColorSpec, *, background: bool) -> str:
    if isinstance(color, str):
        table = _RICH_HIGHLIGHTS if background else _RICH_COLORS
        try:
            return table[color]
        except KeyError as exc:
            kind = "highlight" if background else "color"
            raise KeyError(f"unknown {kind} {color!r}") from exc
    red, green, blue = color
    if background:
        return f"on rgb({red},{green},{blue})"
    return f"rgb({red},{green},{blue})"
def _build_style(
    color: ColorSpec | None,
    on_color: ColorSpec | None,
    attrs: Iterable[str] | None,
) -> Style | None:
    parts: list[str] = []
    if color is not None:
        parts.append(_color_token(color, background=False))
    if on_color is not None:
        parts.append(_color_token(on_color, background=True))
    if attrs is not None:
        for attr in attrs:
            try:
                parts.append(_RICH_ATTRIBUTES[attr])
            except KeyError as exc:
                raise KeyError(f"unknown attribute {attr!r}") from exc
    if not parts:
        return None
    return Style.parse(" ".join(parts))
def _render(text: str, style: Style) -> str:
    buffer = StringIO()
    console = Console(
        file=buffer,
        force_terminal=True,
        color_system=_terminal_color_system(),
        highlight=False,
        soft_wrap=True,
        no_color=False,
        markup=False,
    )
    console.print(Text(text, style=style), end="")
    return buffer.getvalue()
def colored(
    text: object,
    color: ColorSpec | None = None,
    on_color: ColorSpec | None = None,
    attrs: Iterable[str] | None = None,
    *,
    no_color: bool | None = None,
    force_color: bool | None = None,
) -> str:
    result = str(text)
    if not can_colorize(no_color=no_color, force_color=force_color):
        return result
    style = _build_style(color, on_color, attrs)
    if style is None:
        return result
    return _render(result, style)
def cprint(
    text: object,
    color: ColorSpec | None = None,
    on_color: ColorSpec | None = None,
    attrs: Iterable[str] | None = None,
    *,
    no_color: bool | None = None,
    force_color: bool | None = None,
    **kwargs: Any,
) -> None:
    print(
        colored(
            text,
            color,
            on_color,
            attrs,
            no_color=no_color,
            force_color=force_color,
        ),
        **kwargs,
    )
__all__ = [
    "ATTRIBUTES",
    "COLORS",
    "HIGHLIGHTS",
    "RESET",
    "can_colorize",
    "colored",
    "cprint",
]
