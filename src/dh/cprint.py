"""Modern cprint: rich-based colored printing with ANSI-256 cube support."""

from __future__ import annotations
import colorsys
from enum import IntEnum
import io
import math
import os
import random
import sys
from typing import IO, Any, Final, Sequence, TypeAlias

from rich.color import Color, ColorParseError
from rich.console import Console
from rich.style import Style
from rich.text import Text


__all__: list[str] = [
    "Ansi",
    "ColorSpec",
    "Cube",
    "ansi_to_rgb",
    "colored",
    "cprint",
    "cprint_compat",
    "cstr",
    "cube",
    "gray",
    "rainbow",
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
    """The standard 16 ANSI colors, ordered by their palette indices."""

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
    """Return the ANSI 256 palette index for a 6×6×6 cube coordinate."""
    return _CUBE_BASE + 36 * r + 6 * g + b


class Cube(IntEnum):
    """Commonly used colors in the ANSI 256-color cube."""

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
    """Return a cube palette index; each coordinate must be an integer from 0 to 5."""
    for name, value in (("r", r), ("g", g), ("b", b)):
        if not isinstance(value, int) or not 0 <= value <= 5:
            msg = f"cube {name} must be int 0..5, got {value!r}"
            raise ValueError(msg)
    return _cube_idx(r, g, b)


def gray(level: int) -> int:
    """Return a grayscale palette index for a level from 0 to 23."""
    if not isinstance(level, int) or not 0 <= level < _GRAY_COUNT:
        msg = f"gray level must be int 0..23, got {level!r}"
        raise ValueError(msg)
    return _GRAY_BASE + level


def ansi_to_rgb(n: int) -> tuple[int, int, int]:
    """Convert an ANSI 256-color palette index to an RGB triple."""
    if not isinstance(n, int) or not 0 <= n <= 255:
        msg = f"ANSI index must be int 0..255, got {n!r}"
        raise ValueError(msg)
    if n < 16:
        return _ANSI_16_RGB[n]
    if n < 232:
        index = n - 16
        return (
            _CUBE_LEVELS[index // 36],
            _CUBE_LEVELS[(index // 6) % 6],
            _CUBE_LEVELS[index % 6],
        )
    value = 8 + (n - 232) * 10
    return (value, value, value)


def _dist2(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    """Return the squared Euclidean distance between two RGB triples."""
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def rgb_to_ansi256(r: int, g: int, b: int) -> int:
    """Return the closest ANSI 256-color index to an RGB triple."""
    for name, value in (("r", r), ("g", g), ("b", b)):
        if not isinstance(value, int) or not 0 <= value <= 255:
            msg = f"RGB {name} must be int 0..255, got {value!r}"
            raise ValueError(msg)
    target = (r, g, b)
    best_idx = 16
    best_dist = _dist2(ansi_to_rgb(16), target)
    for red in range(6):
        for green in range(6):
            for blue in range(6):
                index = _cube_idx(red, green, blue)
                distance = _dist2(ansi_to_rgb(index), target)
                if distance < best_dist:
                    best_idx, best_dist = index, distance
    for level in range(_GRAY_COUNT):
        index = gray(level)
        distance = _dist2(ansi_to_rgb(index), target)
        if distance < best_dist:
            best_idx, best_dist = index, distance
    return best_idx


# --- Color resolution ---
ColorSpec: TypeAlias = str | int | tuple[int, int, int] | Ansi | Cube | Color
"""A color accepted by the public printing functions."""
# termcolor-era names rich's parser rejects -> nearest valid name (grey/gray: bright_black, SGR 90).
_LEGACY_ALIASES: Final[dict[str, str]] = {
    "grey": "bright_black",
    "gray": "bright_black",
    "dark_grey": "bright_black",
    "light_grey": "white",
    "light_red": "bright_red",
    "light_yellow": "bright_yellow",
    "light_blue": "bright_blue",
    "light_magenta": "bright_magenta",
    "light_cyan": "bright_cyan",
}


def _resolve_color(spec: ColorSpec) -> Color:
    """Convert a supported color specification to a Rich ``Color``."""
    if isinstance(spec, Color):
        return spec
    if isinstance(spec, (Ansi, Cube)):
        return Color.from_ansi(int(spec))
    if isinstance(spec, int):
        if not 0 <= spec <= 255:
            msg = f"ANSI index must be int 0..255, got {spec!r}"
            raise ValueError(msg)
        return Color.from_ansi(spec)
    if isinstance(spec, tuple):
        if len(spec) != 3 or any(not isinstance(value, int) or not 0 <= value <= 255 for value in spec):
            msg = f"RGB tuple must be 3 ints 0..255, got {spec!r}"
            raise ValueError(msg)
        return Color.from_rgb(*spec)
    if isinstance(spec, str):
        normalized = spec.strip().lower()
        if normalized.startswith("cube(") and normalized.endswith(")"):
            parts = [int(part.strip()) for part in normalized[5:-1].split(",")]
            if len(parts) != 3:
                msg = f"cube() expects 3 int args, got {spec!r}"
                raise ValueError(msg)
            return Color.from_ansi(cube(*parts))
        if normalized.startswith("gray(") and normalized.endswith(")"):
            level = int(normalized[5:-1].strip())
            return Color.from_ansi(gray(level))
        if normalized.startswith("ansi(") and normalized.endswith(")"):
            index = int(normalized[5:-1].strip())
            return _resolve_color(index)
        if normalized.startswith("rgb(") and normalized.endswith(")"):
            parts = [int(part.strip()) for part in normalized[4:-1].split(",")]
            if len(parts) != 3:
                msg = f"rgb() expects 3 int args, got {spec!r}"
                raise ValueError(msg)
            return Color.from_rgb(*parts)
        try:
            return Color.parse(spec)
        except ColorParseError as exc:  # Color.parse raises, it never returns None
            if spec in _LEGACY_ALIASES:
                return _resolve_color(_LEGACY_ALIASES[spec])
            msg = f"could not parse color: {spec!r}"
            raise ValueError(msg)
    msg = f"unsupported color spec: {type(spec).__name__}"
    raise TypeError(msg)


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
    """Build a Rich style from color and text-attribute options."""
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


def _make_console(
    file: IO[str] | None,
    force_terminal: bool | None,
) -> Console:
    """Create a Rich console configured for plain, non-markup text."""
    return Console(
        file=file,
        force_terminal=force_terminal,
        highlight=False,
        emoji=False,
        markup=False,
        soft_wrap=True,
    )


def _env_forces_no_color() -> bool:
    """Return whether the environment explicitly requests no color."""
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
    """Return text wrapped in ANSI SGR codes matching the requested style.
    If ``no_color`` is ``None``, the ``NO_COLOR`` environment variable is
    honored. Set it to ``True`` to return plain text or ``False`` to force
    ANSI output.
    """
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
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=True,
        color_system="truecolor",
        highlight=False,
        emoji=False,
        markup=False,
        soft_wrap=True,
    )
    console.print(Text(text, style=style), end="")
    return buffer.getvalue()


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
    """Print joined arguments with Rich styling and ANSI-256 color support."""
    text = sep.join(str(arg) for arg in args)
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
    """Return the ANSI-encoded string that ``cprint`` would emit."""
    return colored(
        sep.join(str(arg) for arg in args),
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


def cprint_compat(
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
    """Print with support for the legacy positional color syntax.
    For example, ``cprint_compat("text", "cyan")`` is treated as
    ``cprint("text", color="cyan")``. A third legacy string argument is
    treated as a background color when no explicit ``bg`` is supplied.
    """
    new_args = args
    if color is None and 2 <= len(args) <= 3 and isinstance(args[1], str) and args[1].lower() in _LEGACY_COLORS:
        color = args[1]
        new_args = (args[0],)
        if len(args) == 3:
            third_arg = args[2]
            if bg is None and isinstance(third_arg, str):
                bg = third_arg[3:] if third_arg.lower().startswith("on_") else third_arg
            else:
                new_args = (args[0], third_arg)
    cprint(
        *new_args,
        color=color,
        bg=bg,
        bold=bold,
        dim=dim,
        italic=italic,
        underline=underline,
        blink=blink,
        reverse=reverse,
        strike=strike,
        sep=sep,
        end=end,
        file=file,
        flush=flush,
        console=console,
        force_terminal=force_terminal,
    )


def lerp(a: Any, b: int, t: Any):
    return a + (b - a) * t


def blend(c1: Sequence[Any], c2: Sequence[Any], t: float) -> str:
    t = t**1.47
    t = 0.82 * t + 0.08 * math.sin(3.2 * t)
    r = int(lerp(c1[0], c2[0], t))
    g = int(lerp(c1[1], c2[1], t))
    b = int(lerp(c1[2], c2[2], t))
    return f"#{r:02x}{g:02x}{b:02x}"


def rainbow(txt: str) -> None:
    console = Console()
    fixed_palettes = [
        [
            (0x2E, 0x7B, 0xEA),
            (0x6C, 0x5B, 0xD8),
            (0xB6, 0x6D, 0xB9),
            (0xE8, 0x8A, 0xA6),
            (0xFF, 0xB6, 0xC1),
        ],
        [
            (0x33, 0xE0, 0xA1),
            (0x19, 0xB6, 0xD8),
            (0x2A, 0xD5, 0x6C),
            (0x15, 0x90, 0xD3),
            (0x0D, 0x75, 0xB4),
        ],
        [
            (0x00, 0xFF, 0xCC),
            (0x00, 0xDD, 0xFF),
            (0x66, 0x99, 0xFF),
            (0xAA, 0x77, 0xFF),
            (0xFF, 0x66, 0xDD),
        ],
        [
            (0x3A, 0x0C, 0xF0),
            (0x66, 0x1B, 0xF6),
            (0x98, 0x2D, 0xFF),
            (0xF2, 0x36, 0xA3),
            (0xFF, 0x73, 0x3F),
        ],
        [
            (0x07, 0x1A, 0x40),
            (0x2E, 0x7B, 0xEA),
            (0x7C, 0x4D, 0xFF),
            (0xFF, 0x6B, 0x6B),
            (0xFF, 0xF1, 0xD6),
        ],
        [
            (0x12, 0xB8, 0xFF),
            (0x2E, 0x7B, 0xEA),
            (0x6C, 0x5B, 0xD8),
            (0xC2, 0x4B, 0xC3),
            (0xFF, 0x88, 0xA8),
        ],
    ]
    _sysrand = random.SystemRandom()
    idx_env = os.getenv("PALETTE_NUM")
    if idx_env is not None:
        try:
            idx = int(idx_env)
            if 0 <= idx < len(fixed_palettes):
                palette = list(fixed_palettes[idx])
            else:
                raise ValueError
        except Exception:
            palette = None
    else:
        palette = None
    if palette is None:
        N = 5
        base_h = _sysrand.random()
        spacing = 1.0 / N
        sat_center = 0.72 + (_sysrand.random() - 0.5) * 0.2
        val_center = 0.78 + (_sysrand.random() - 0.5) * 0.2
        palette = []
        for i in range(N):
            jitter = (_sysrand.random() - 0.5) * (spacing * 0.6)
            h = (base_h + i * spacing + jitter) % 1.0
            s = min(max(sat_center + (_sysrand.random() - 0.5) * 0.18, 0.35), 1.0)
            v = min(max(val_center + (_sysrand.random() - 0.5) * 0.18, 0.35), 1.0)
            r_f, g_f, b_f = colorsys.hsv_to_rgb(h, s, v)
            r, g, b = round(r_f * 255), round(g_f * 255), round(b_f * 255)
            palette.append((r, g, b))
        if _sysrand.random() < 0.25:
            delta_v = (_sysrand.random() - 0.5) * 0.18
            new_palette = []
            for r, g, b in palette:
                h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                v = min(max(v + delta_v, 0.2), 1.0)
                rr, gg, bb = colorsys.hsv_to_rgb(h, s, v)
                new_palette.append((round(rr * 255), round(gg * 255), round(bb * 255)))
            palette = new_palette
    _sysrand.shuffle(palette)
    if isinstance(txt, list):
        txt = "\n".join(txt)
    text = txt.strip().split("\n")
    H = len(text)
    for i, line in enumerate(text):
        tline = Text()
        W = len(line)
        for j, ch in enumerate(line):
            raw = i * 0.72 + j * 0.44
            t = raw / (H * 0.72 + W * 0.44)
            seg = t * (len(palette) - 1)
            idx = int(seg)
            t2 = seg - idx
            c1 = palette[idx]
            c2 = palette[min(idx + 1, len(palette) - 1)]
            tline.append(ch, style=blend(c1, c2, t2))
        console.print(tline)


def type_writer(text: str, speed: float = 0.03, style: str = "green") -> None:
    for char in text:
        console.print(char, end="", style=style)
        time.sleep(speed)
    print()
