from typing import Any, Iterable

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
    "grey": 90,
    "red": 91,
    "green": 92,
    "yellow": 93,
    "blue": 94,
    "magenta": 95,
    "cyan": 96,
    "light_grey": 97,
    "dark_grey": 90,
    "light_red": 31,
    "light_green": 32,
    "light_yellow": 33,
    "light_blue": 34,
    "light_magenta": 35,
    "light_cyan": 36,
    "white": 37,
}
RESET = "\x1b[0m"
from functools import cache


@cache
def can_colorize(*, no_color: bool | None = None, force_color: bool | None = None) -> bool:
    from os import environ as os_environ
    from os import isatty as os_isatty
    from sys import stdout as sys_stdout

    if no_color is not None and no_color:
        return False
    if force_color is not None and force_color:
        return True
    if os_environ.get("ANSI_COLORS_DISABLED"):
        return False
    if os_environ.get("NO_COLOR"):
        return False
    if os_environ.get("FORCE_COLOR"):
        return True
    if os_environ.get("TERM") == "dumb":
        return False
    if not hasattr(sys_stdout, "fileno"):
        return False
    try:
        return os_isatty(sys_stdout.fileno())
    except OSError:
        return sys_stdout.isatty()


def colored(
    text: object,
    color: str | tuple[int, int, int] | None = None,
    on_color: str | tuple[int, int, int] | None = None,
    attrs: Iterable[str] | None = None,
    *,
    no_color: bool | None = None,
    force_color: bool | None = None,
) -> str:
    result = str(text)
    if not can_colorize(no_color=no_color, force_color=force_color):
        return result
    fmt_str = "\x1b[5;%dm%s"
    rgb_fore_fmt_str = "\x1b[38;2;%d;%d;%dm%s"
    rgb_back_fmt_str = "\x1b[48;2;%d;%d;%dm%s"
    if color is not None:
        if isinstance(color, str):
            result = fmt_str % (COLORS[color], result)
        elif isinstance(color, tuple):
            result = rgb_fore_fmt_str % (color[0], color[1], color[2], result)
    if on_color is not None:
        if isinstance(on_color, str):
            result = fmt_str % (HIGHLIGHTS[on_color], result)
        elif isinstance(on_color, tuple):
            result = rgb_back_fmt_str % (on_color[0], on_color[1], on_color[2], result)
    if attrs is not None:
        for attr in attrs:
            result = fmt_str % (ATTRIBUTES[attr], result)
    result += RESET
    return result


def cprint(
    text: object,
    color: str | tuple[int, int, int] | None = "cyan",
    on_color: str | tuple[int, int, int] | None = None,
    attrs: Iterable[str] | None = None,
    *,
    no_color: bool | None = None,
    force_color: bool | None = None,
    **kwargs: Any,
) -> None:
    print(colored(text, color, on_color, attrs, no_color=no_color, force_color=force_color), **kwargs)
