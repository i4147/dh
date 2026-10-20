from __future__ import annotations

import itertools
import random
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterable, Optional, Self, Sequence, TextIO

DEFAULT_MESSAGES: tuple[str, ...] = (
    "asking Terry",
    "argmaxing",
    "bootstrapping",
    "backpropagating",
    "consulting the oracle",
    "embedding your intent",
    "sampling from the posterior",
    "warming up the GPUs",
    "aligning the vibes",
    "tokenizing reality",
    "gradient descending",
    "attending to your request",
    "spinning up the sandbox",
    "negotiating with the compiler",
    "herding probabilities",
    "compressing the universe",
    "asking the second Terry",
    "doing linear algebra, probably",
    "resolving merge conflicts in my head",
    "checking the math twice",
    "untangling dependencies",
    "hallucinating responsibly",
    "routing through 47 experts",
    "caching something clever",
    "reticulating splines",
    "double-checking the obvious",
    "counting to one, very slowly",
    "polishing the tokens",
    "thinking about thinking",
    "asking Terry for a hint",
    "squashing bugs (lovingly)",
    "measuring twice, cutting once",
    "flipping bits",
    "lowering the temperature",
    "raising the temperature back",
    "searching the latent space",
    "grep-ing the docs",
    "pretending this was easy",
    "almost there, probably",
)
SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class StatusLine:
    def __init__(
        self,
        messages: Optional[Iterable[str]] = None,
        *,
        interval: float = 1.8,
        fps: float = 12.0,
        spinner: str = SPINNER_FRAMES,
        stream: Optional[TextIO] = None,
        rng: Optional[random.Random] = None,
        suffix: str = "...",
        hide_cursor: bool = True,
    ) -> None:
        self.messages: Sequence[str] = tuple(messages) if messages else DEFAULT_MESSAGES
        if not self.messages:
            msg = "messages must not be empty"
            raise ValueError(msg)
        self.interval = interval
        self.delay = 1.0 / max(fps, 1.0)
        self.suffix = suffix
        self.stream: TextIO = stream if stream is not None else sys.stderr
        self.hide_cursor = hide_cursor
        self._frames = itertools.cycle(spinner) if spinner else itertools.repeat("")
        self._rng = rng or random.Random()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._current = ""
        self._last_pick: Optional[str] = None
        self._drawn_width = 0
        self._is_tty = bool(getattr(self.stream, "isatty", lambda: False)())

    def start(self) -> "StatusLine":
        if self._thread is not None:
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="StatusLine", daemon=True)
        self._thread.start()
        return self

    def stop(self, *, final: Optional[str] = None) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=2.0)
        self._thread = None
        self._clear()
        if final:
            self.stream.write(final + "\n")
            self.stream.flush()

    def set_message(self, message: str) -> None:
        with self._lock:
            self._current = message
            self._last_pick = message

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, *exc_info) -> bool:
        self.stop()
        return False

    def _pick(self) -> str:
        if len(self.messages) == 1:
            return self.messages[0]
        choice = self._rng.choice(self.messages)
        while choice == self._last_pick:
            choice = self._rng.choice(self.messages)
        self._last_pick = choice
        return choice

    def _run(self) -> None:
        next_switch = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            with self._lock:
                if now >= next_switch or not self._current:
                    self._current = self._pick()
                    next_switch = now + self.interval
                msg = self._current
            frame = next(self._frames)
            text = f"{frame} {msg}{self.suffix}".strip()
            self._render(text)
            self._stop.wait(self.delay)

    def _render(self, text: str) -> None:
        if not self._is_tty:
            return
        text = self._fit(text)
        pad = " " * max(0, self._drawn_width - len(text))
        try:
            self.stream.write("\r" + text + pad)
            self.stream.flush()
        except (ValueError, OSError):
            self._is_tty = False
            return
        self._drawn_width = len(text)

    def _clear(self) -> None:
        if not self._is_tty or not self._drawn_width:
            self._drawn_width = 0
            return
        try:
            self.stream.write("\r" + " " * self._drawn_width + "\r")
            self.stream.flush()
        except (ValueError, OSError):
            pass
        self._drawn_width = 0

    def _fit(self, text: str) -> str:
        cols = shutil.get_terminal_size((80, 24)).columns
        limit = max(12, cols - 1)
        if len(text) > limit:
            text = text[: limit - 1] + "…"
        return text


@contextmanager
def thinking(messages: Optional[Iterable[str]] = None, **kwargs):
    line = StatusLine(messages, **kwargs)
    line.start()
    try:
        yield line
    finally:
        line.stop()


def _demo() -> None:
    rng = random.Random()
    print("Simulating an agent working on your prompt...\n", file=sys.stderr)
    with StatusLine(interval=1.4) as status:
        time.sleep(rng.uniform(3, 5))
        status.set_message("searching the web")
        time.sleep(2.0)
        status.set_message("")
        time.sleep(rng.uniform(3, 5))
    print("\nDone. Here's your answer: 42", file=sys.stderr)


if __name__ == "__main__":
    try:
        _demo()
    except KeyboardInterrupt:
        sys.stderr.write("\n")
