"""Small regression checks for exported utility helpers."""
from pathlib import Path
import hashlib

import pytest
from dh import fileutils
from dh.jobutils import Method, failures, mpf, values
from dh.utils import clean_terminal_transcript, cube_rgb, get_sha256, is_valid_url


def test_utilities(tmp_path: Path) -> None:
    path = tmp_path / 'data'
    path.write_bytes(b'hello')
    assert get_sha256(path) == hashlib.sha256(b'hello').hexdigest()
    assert cube_rgb(16) == (0, 0, 0)
    assert clean_terminal_transcript('\x1b]0;title\x07hi\rbye\n') == 'bye\n'
    assert fileutils.is_git_repo(tmp_path) is False
    image = tmp_path / 'test.png'
    image.write_bytes(b'')
    assert fileutils.is_image(image)


@pytest.mark.parametrize('url', [None, '', 'bad', 'ftp://example.com'])
def test_invalid_url(url: str | None) -> None:
    assert not is_valid_url(url)


def test_valid_url() -> None:
    assert is_valid_url('https://example.com')


def test_thread_execution() -> None:
    results = mpf(lambda x: x * 2, [1, 2, 3], method=Method.THREAD, progress=None)
    assert values(results) == [2, 4, 6]
    assert failures(results) == []
