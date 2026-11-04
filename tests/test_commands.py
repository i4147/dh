"""Subprocess output, errors, and timeouts share clean transcript semantics."""
import sys
from pathlib import Path

import pytest
from dh.fileutils import runcmd


def test_clean_output_and_emit(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = runcmd([sys.executable, '-c',
        "import sys; sys.stdout.write('\\x1b[31mred\\x1b[0m\\rfinal  \\n'); "
        "sys.stderr.write('bad\\b!\\n'); sys.exit(3)"])
    assert (code, out, err) == (3, 'final\n', 'ba!\n')
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == (out, err)


def test_silent_and_empty(capsys: pytest.CaptureFixture[str]) -> None:
    assert runcmd([sys.executable, '-c', 'pass'], False) == (0, '', '')
    assert capsys.readouterr() == ('', '')


def test_missing(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = runcmd(['/no/such/dh-command'], False)
    assert code == 127 and out == '' and 'Command not found' in err
    assert capsys.readouterr() == ('', '')


def test_permission(tmp_path: Path) -> None:
    target = tmp_path / 'not-executable'
    target.write_text('hello')
    assert runcmd([str(target)], False)[0] == 126


def test_timeout_preserves_partial_output() -> None:
    code, out, err = runcmd([sys.executable, '-c',
        "import time; print('\\x1b[32mready\\x1b[0m', flush=True); time.sleep(5)"],
        False, timeout=0.2)
    assert code == 124 and out == 'ready\n' and 'timed out' in err


@pytest.mark.parametrize('cmd, exception', [([], ValueError), ([''], ValueError), ([1], TypeError)])
def test_invalid_commands(cmd: list, exception: type[Exception]) -> None:
    with pytest.raises(exception):
        runcmd(cmd, False)


def test_shell_string_is_rejected() -> None:
    with pytest.raises(TypeError):
        runcmd("echo hello", False)


def test_os_error_uses_clean_diagnostic(monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    import subprocess
    def broken(*args: object, **kwargs: object) -> None:
        raise OSError("\x1b[31mbroken\x1b[0m")
    monkeypatch.setattr(subprocess, "run", broken)
    code, out, err = runcmd(["command"])
    assert code == 1 and out == "" and "broken" in err and "\x1b" not in err
    assert capsys.readouterr().err == err
