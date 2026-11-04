"""Classification and constant-table integrity regression checks."""
import ast
import builtins
import keyword
from pathlib import Path
import sys

import pytest
from dh import const
from dh.fileutils import is_binary, is_text_file


@pytest.mark.parametrize('extension', ['.pyc', '.class', '.doc', '.docx', '.qm', '.vsmacros'])
def test_compiled_and_container_formats_are_binary(tmp_path: Path, extension: str) -> None:
    assert extension in const.BINARY_EXTENSIONS
    assert extension not in const.TEXT_EXTENSIONS
    path = tmp_path / ('file' + extension.upper())
    path.write_bytes(b'container')
    assert is_binary(path)


@pytest.mark.parametrize('extension', ['.tsv', '.ass', '.pem', '.xbm', '.xpm', '.afm',
                                      '.bdf', '.dae', '.dxf', '.mhtml', '.sum'])
def test_text_formats(tmp_path: Path, extension: str) -> None:
    assert extension in const.TEXT_EXTENSIONS
    assert extension not in const.BINARY_EXTENSIONS
    path = tmp_path / ('file' + extension.upper())
    path.write_text('plain text\n')
    assert is_text_file(path)


@pytest.mark.parametrize('extension', ['.ts', '.plist', '.stl', '.obj', '.fbx', '.pot',
                                      '.mod', '.pth', '.pbm', '.pgm', '.ppm', '.cer'])
def test_ambiguous_extensions_use_content(tmp_path: Path, extension: str) -> None:
    assert extension not in const.TEXT_EXTENSIONS | const.BINARY_EXTENSIONS
    path = tmp_path / ('file' + extension)
    path.write_text('some textual content\n')
    assert is_text_file(path)
    path.write_bytes(b'\x00' * 100)
    assert is_binary(path)


def test_extension_invariants() -> None:
    assert const.TEXT_EXTENSIONS.isdisjoint(const.BINARY_EXTENSIONS)
    for name, value in vars(const).items():
        if name.endswith('_EXTENSIONS'):
            assert isinstance(value, frozenset)
            assert all(ext.startswith('.') and ext == ext.lower() for ext in value)
            assert all(not any(char in ext for char in '*?[]') for ext in value)


@pytest.mark.parametrize('name', ['README', 'Makefile', '.gitignore', '.env'])
def test_text_filenames(tmp_path: Path, name: str) -> None:
    assert name.lower() in const.TEXT_FILENAMES
    path = tmp_path / name
    path.write_text('text')
    assert is_text_file(path)


def test_runtime_vocabulary() -> None:
    assert const.STDLIB == sys.stdlib_module_names
    assert set(keyword.kwlist) <= const.PY_KEYWORDS
    assert set(keyword.softkwlist) <= const.PY_KEYWORDS
    assert set(dir(builtins)) <= const.PY_KEYWORDS
    assert {'execfile', 'xrange', 'basestring', 'boolean'}.isdisjoint(const.PY_KEYWORDS)


def test_skip_dirs_do_not_hide_source_packages(tmp_path: Path) -> None:
    from dh import get_files
    names = {'numpy', 'pandas', 'pip', 'scipy', 'mypy', 'cython'}
    assert names.isdisjoint(const.SKIP_DIRS)
    for name in names:
        (tmp_path / name).mkdir()
        (tmp_path / name / 'source.py').touch()
    assert len(get_files(tmp_path, ext=['py'])) == len(names)


def test_colors_and_mime() -> None:
    assert const.CSS_COLORS['aliceblue'] == (240, 248, 255)
    assert const.CSS_COLORS['midnightblue'] == (25, 25, 112)
    assert const.CSS_COLORS['rebeccapurple'] == (102, 51, 153)
    assert len(const.CSS_COLORS) == 148
    assert all(len(rgb) == 3 and all(0 <= value <= 255 for value in rgb)
               for rgb in const.CSS_COLORS.values())
    assert const.YELLOW == '\x1b[1;33m' == const.yellow
    assert const.GREYWHITE == '\x1b[2m' == const.greywhite
    assert const.EXT2MIME['.otf'] == 'font/otf'


def test_constant_dicts_have_no_duplicate_keys() -> None:
    tree = ast.parse(Path(const.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [ast.literal_eval(key) for key in node.keys if key is not None]
            assert len(keys) == len(set(keys))


def test_uppercase_image_extension(tmp_path: Path) -> None:
    from dh.fileutils import is_image
    path = tmp_path / 'image.PNG'
    path.touch()
    assert is_image(path)
