"""Modern cprint: rich-based colored printing with ANSI-256 cube support."""

from __future__ import annotations

import io
import os
import sys
from enum import IntEnum
from typing import IO, Final, TypeAlias

from rich.color import Color
from rich.console import Console
from rich.style import Style
from rich.text import Text

__all__ = [
    "Ansi",
    "Cube",
    "ColorSpec",
    "ansi_to_rgb",
    "colored",
    "cprint",
    "cprint_compat",
    "cstr",
    "cube",
    "gray",
    "rgb_to_ansi256",
]

# --- ANSI 256 palette tables ---

_ANSI_16_RGB: Final[tuple[tuple[int, int, int], ...]] = (
    (0, 0, 0),
    (128, 0, 0),
    (0, 128, 0),
    (128, 128, 0),
    (0, 0, 128),
    (128, 0, 128),
    (0, 128, 128),
    (192, 192, 192),
    (128, 128, 128),
    (255, 0, 0),
    (0, 255, 0),
    (255, 255, 0),
    (0, 0, 255),
    (255, 0, 255),
    (0, 255, 255),
    (255, 255, 255),
)
_CUBE_LEVELS: Final[tuple[int, ...]] = (0, 95, 135, 175, 215, 255)
_CUBE_BASE: Final[int] = 16
_GRAY_BASE: Final[int] = 232
_GRAY_COUNT: Final[int] = 24


# --- Named color enums ---


class Ansi(IntEnum):
    """Standard ANSI 16 colors (SGR 30-37, 90-97)."""

    BLACK = 0
    RED = 1
    GREEN = 2
    YELLOW = 3
    BLUE = 4
    MAGENTA = 5
    CYAN = 6
    WHITE = 7
    BRIGHT_BLACK = 8
    BRIGHT_RED = 9
    BRIGHT_GREEN = 10
    BRIGHT_YELLOW = 11
    BRIGHT_BLUE = 12
    BRIGHT_MAGENTA = 13
    BRIGHT_CYAN = 14
    BRIGHT_WHITE = 15


def _cube_idx(r: int, g: int, b: int) -> int:
    return _CUBE_BASE + 36 * r + 6 * g + b


class Cube(IntEnum):
    """Common ANSI 256 6x6x6 cube indices."""

    BLACK = 16
    RED = _cube_idx(5, 0, 0)  # 196
    GREEN = _cube_idx(0, 5, 0)  # 46
    BLUE = _cube_idx(0, 0, 5)  # 21
    YELLOW = _cube_idx(5, 5, 0)  # 226
    MAGENTA = _cube_idx(5, 0, 5)  # 201
    CYAN = _cube_idx(0, 5, 5)  # 51
    WHITE = _cube_idx(5, 5, 5)  # 231
    GRAY = _cube_idx(3, 3, 3)  # 145
    ORANGE = _cube_idx(5, 3, 0)  # 214
    PINK = _cube_idx(5, 3, 4)  # 218
    PURPLE = _cube_idx(3, 0, 5)  # 129
    TEAL = _cube_idx(0, 3, 3)  # 37


# --- Palette helpers ---


def cube(r: int, g: int, b: int) -> int:
    """ANSI 256 index for cube coordinate (r, g, b) each in 0..5."""
    for name, v in (("r", r), ("g", g), ("b", b)):
        if not isinstance(v, int) or not 0 <= v <= 5:
            raise ValueError(f"cube {name} must be int 0..5, got {v!r}")
    return _cube_idx(r, g, b)


def gray(level: int) -> int:
    """ANSI 256 index for grayscale level 0..23 (232..255)."""
    if not isinstance(level, int) or not 0 <= level < _GRAY_COUNT:
        raise ValueError(f"gray level must be int 0..23, got {level!r}")
    return _GRAY_BASE + level


def ansi_to_rgb(n: int) -> tuple[int, int, int]:
    """RGB triple for an ANSI 256 index."""
    if not isinstance(n, int) or not 0 <= n <= 255:
        raise ValueError(f"ANSI index must be int 0..255, got {n!r}")
    if n < 16:
        return _ANSI_16_RGB[n]
    if n < 232:
        i = n - 16
        return (_CUBE_LEVELS[i // 36], _CUBE_LEVELS[(i // 6) % 6], _CUBE_LEVELS[i % 6])
    v = 8 + (n - 232) * 10
    return (v, v, v)


def _dist2(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def rgb_to_ansi256(r: int, g: int, b: int) -> int:
    """Closest ANSI 256 index (cube or grayscale) to an RGB triple."""
    for name, v in (("r", r), ("g", g), ("b", b)):
        if not isinstance(v, int) or not 0 <= v <= 255:
            raise ValueError(f"RGB {name} must be int 0..255, got {v!r}")
    target = (r, g, b)
    best_idx, best_dist = 16, _dist2(ansi_to_rgb(16), target)
    for i in range(6):
        for j in range(6):
            for k in range(6):
                idx = _cube_idx(i, j, k)
                d = _dist2(ansi_to_rgb(idx), target)
                if d < best_dist:
                    best_idx, best_dist = idx, d
    for level in range(_GRAY_COUNT):
        idx = gray(level)
        d = _dist2(ansi_to_rgb(idx), target)
        if d < best_dist:
            best_idx, best_dist = idx, d
    return best_idx


# --- Color resolution ---

ColorSpec: TypeAlias = str | int | tuple[int, int, int] | Ansi | Cube | Color


def _resolve_color(spec: ColorSpec) -> Color:
    if isinstance(spec, Color):
        return spec
    if isinstance(spec, (Ansi, Cube)):
        return Color.from_ansi(int(spec))
    if isinstance(spec, int):
        if not 0 <= spec <= 255:
            raise ValueError(f"ANSI index must be int 0..255, got {spec!r}")
        return Color.from_ansi(spec)
    if isinstance(spec, tuple):
        if len(spec) != 3 or any(not isinstance(v, int) or not 0 <= v <= 255 for v in spec):
            raise ValueError(f"RGB tuple must be 3 ints 0..255, got {spec!r}")
        return Color.from_rgb(*spec)
    if isinstance(spec, str):
        s = spec.strip().lower()
        if s.startswith("cube(") and s.endswith(")"):
            parts = [int(p.strip()) for p in s[5:-1].split(",")]
            if len(parts) != 3:
                raise ValueError(f"cube() expects 3 int args, got {spec!r}")
            return Color.from_ansi(cube(*parts))
        if s.startswith("gray(") and s.endswith(")"):
            return Color.from_ansi(gray(int(s[5:-1].strip())))
        if s.startswith("ansi(") and s.endswith(")"):
            return _resolve_color(int(s[5:-1].strip()))
        if s.startswith("rgb(") and s.endswith(")"):
            parts = [int(p.strip()) for p in s[4:-1].split(",")]
            if len(parts) != 3:
                raise ValueError(f"rgb() expects 3 int args, got {spec!r}")
            return Color.from_rgb(*parts)
        parsed = Color.parse(spec)
        if parsed is None:
            raise ValueError(f"could not parse color: {spec!r}")
        return parsed
    raise TypeError(f"unsupported color spec: {type(spec).__name__}")


def _build_style(
    *,
    color: ColorSpec | None,
    bg: ColorSpec | None,
    bold: bool,
    dim: bool,
    italic: bool,
    underline: bool,
    blink: bool,
    reverse: bool,
    strike: bool,
) -> Style:
    return Style(
        color=_resolve_color(color) if color is not None else None,
        bgcolor=_resolve_color(bg) if bg is not None else None,
        bold=bold or None,
        dim=dim or None,
        italic=italic or None,
        underline=underline or None,
        blink=blink or None,
        reverse=reverse or None,
        strike=strike or None,
    )


def _make_console(file: IO[str] | None, force_terminal: bool | None) -> Console:
    return Console(
        file=file,
        force_terminal=force_terminal,
        highlight=False,
        emoji=False,
        markup=False,
        soft_wrap=True,
    )


def _env_forces_no_color() -> bool:
    if "NO_COLOR" in os.environ:
        return True
    if os.environ.get("FORCE_COLOR", "") not in ("", "0", "false", "no"):
        return False
    return False


# --- Public API ---


def colored(
    text: str,
    *,
    color: ColorSpec | None = None,
    bg: ColorSpec | None = None,
    bold: bool = False,
    dim: bool = False,
    italic: bool = False,
    underline: bool = False,
    blink: bool = False,
    reverse: bool = False,
    strike: bool = False,
    no_color: bool | None = None,
) -> str:
    """Return `text` wrapped in ANSI SGR codes matching the style spec.

    no_color=None honors the NO_COLOR / FORCE_COLOR environment variables;
    pass True to force plain text, False to force ANSI output."""
    if not isinstance(text, str):
        text = str(text)
    if no_color is None:
        no_color = _env_forces_no_color()
    if no_color or not text:
        return text
    style = _build_style(
        color=color,
        bg=bg,
        bold=bold,
        dim=dim,
        italic=italic,
        underline=underline,
        blink=blink,
        reverse=reverse,
        strike=strike,
    )
    buf = io.StringIO()
    console = Console(
        file=buf,
        force_terminal=True,
        color_system="truecolor",
        highlight=False,
        emoji=False,
        markup=False,
        soft_wrap=True,
    )
    console.print(Text(text, style=style), end="")
    return buf.getvalue()


def cprint(
    *args: object,
    color: ColorSpec | None = None,
    bg: ColorSpec | None = None,
    bold: bool = False,
    dim: bool = False,
    italic: bool = False,
    underline: bool = False,
    blink: bool = False,
    reverse: bool = False,
    strike: bool = False,
    sep: str = " ",
    end: str = "\n",
    file: IO[str] | None = None,
    flush: bool = False,
    console: Console | None = None,
    force_terminal: bool | None = None,
) -> None:
    """Colored print. A drop-in superset of builtins.print with ANSI-256 styling."""
    text = sep.join(str(a) for a in args)
    style = _build_style(
        color=color,
        bg=bg,
        bold=bold,
        dim=dim,
        italic=italic,
        underline=underline,
        blink=blink,
        reverse=reverse,
        strike=strike,
    )
    if console is None:
        console = _make_console(file, force_terminal)
    console.print(Text(text, style=style), end=end)
    if flush:
        console.file.flush()


def cstr(
    *args: object,
    color: ColorSpec | None = None,
    bg: ColorSpec | None = None,
    bold: bool = False,
    dim: bool = False,
    italic: bool = False,
    underline: bool = False,
    blink: bool = False,
    reverse: bool = False,
    strike: bool = False,
    sep: str = " ",
) -> str:
    """Return the same styled output cprint would emit, as an ANSI-encoded str."""
    return colored(
        sep.join(str(a) for a in args),
        color=color,
        bg=bg,
        bold=bold,
        dim=dim,
        italic=italic,
        underline=underline,
        blink=blink,
        reverse=reverse,
        strike=strike,
        no_color=False,
    )


_LEGACY_COLORS: Final[frozenset[str]] = frozenset({
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    "grey",
    "gray",
    "light_red",
    "light_green",
    "light_yellow",
    "light_blue",
    "light_magenta",
    "light_cyan",
    "dark_grey",
    "light_grey",
})


def cprint_compat(*args: object, color: ColorSpec | None = None, bg: ColorSpec | None = None, **kwargs: object) -> None:
    """Backward-compat shim: cprint('text', 'cyan') → cprint('text', color='cyan')."""
    if color is None and 2 <= len(args) <= 3 and isinstance(args[1], str) and args[1].lower() in _LEGACY_COLORS:
        color = args[1]
        new_args = (args[0],)
        if len(args) == 3 and bg is None and isinstance(args[2], str):
            v = args[2]
            bg = v[3:] if v.lower().startswith("on_") else v
        else:
            new_args = args
        cprint(*new_args, color=color, bg=bg, **kwargs)  # type: ignore[arg-type]
        return
    cprint(*args, color=color, bg=bg, **kwargs)  # type: ignore[arg-type]
