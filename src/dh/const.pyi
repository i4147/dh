from __future__ import annotations
from typing import Final

SHEBANG_MAP: dict[str, str]
BIN_EXT: frozenset
TXT_EXT: frozenset
IMGEXT: frozenset
PKG_MAPPING: dict
EXT2MIME: dict
MIME2EXT: dict
PY_KEYWORDS: frozenset
AREXT: frozenset
AUDEXT: frozenset
BOOKEXT: frozenset
DOCEXT: frozenset
FONTEXT: frozenset
VIDEXT: frozenset
CODEXT: frozenset
STDLIB: frozenset
CSS_COLORS: dict
RESET: str = "\x1b[0m"
reset: str
BOLD: str = "\x1b[1m"
bold: str
UNDERLINE: str = "\x1b[4m"
underline: str
BLINK: str = "\x1b[5m"
blink: str
REVERSE: str = "\x1b[7m"
reverse: str
CONSEALED: str = "\x1b[8m"
consealed: str
RED: str = "\x1b[1;31m"
red: str
GREEN: str = "\x1b[1;32m"
green: str
YELLOW: str = "\x1b[1;239;236;11m"
yellow: str
BLUE: str = "\x1b[1;34m"
blue: str
MAGENTA: str = "\x1b[1;35m"
magenta: str
CYAN: str = "\x1b[1;36m"
cyan: str
WHITE: str = "\x1b[1;37m"
white: str
BLACK: str = "\x1b[1;30m"
black: str
LRED: str = "\x1b[1;91m"
lred: str
LGREEN: str = "\x1b[1;92m"
lgreen: str
LYELLOW: str = "\x1b[1;93m"
lyellow: str
LBLUE: str = "\x1b[1;94m"
lblue: str
LMAGENTA: str = "\x1b[1;95m"
lmagenta: str
LCYAN: str = "\x1b[1;96m"
lcyan: str
GREY: str = "\x1b[38;2;147;147;147m"
grey: str
GREYWHITE: str = "\\033[2m"
greywhite: str
GREYBLACK: str = "\x1b[1;90m"
greyblack: str
ANSI_RESET: str = "\x1b[0m"
ANSI_BOLD: str = "\x1b[1m"
CHUNK_SIZE: Final = 32768
ZERO_DOT_THREE: Final = 0.3
SKIP_DIRS: frozenset[str]
THRESHOLD: Final = 2097152
SDCARD: str = "/sdcard"
EMULATED: str = "/storage/emulated/0"
CONTEXT_METHOD: str = "spawn"
MAX_WORKERS: Final = 4
DOC_TH1: str = '"""'
DOC_TH2: str = "'''"
DOC_TH: tuple[str, str]
