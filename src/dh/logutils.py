import logging
import sys
from pathlib import Path


def init_logger(
    name: str | None,
    level: int = logging.INFO,
    log_file: str | Path | None = None,
    fmt: str = "[%(levelname)s] %(message)s",
    datefmt: str | None = None,
    console: bool = True,
    file_mode: str = "w",
    encoding: str = "utf-8",
    propagate: bool = False,
    handlers: list[logging.Handler] | None = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = propagate
    if logger.handlers:
        for h in logger.handlers[:]:
            logger.removeHandler(h)
    if handlers is None:
        handlers = []
        if console:
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(level)
            ch.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
            handlers.append(ch)
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_path, mode=file_mode, encoding=encoding)
            fh.setLevel(level)
            fh.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
            handlers.append(fh)
    for h in handlers:
        logger.addHandler(h)
    return logger
