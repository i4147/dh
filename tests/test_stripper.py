from __future__ import annotations
import ast
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from strip_python import ASTStripper, CSTStripper, TSStripper, remove_blank_lines
SCRIPT = Path(__file__).with_name("strip_python.py")
class StripTests(unittest.TestCase):
    def test_ast_keeps_original_layout(self) -> None:
        source = "# discard\nπ  =  {'x':  1}  # discard\ndef f( x=1 ):\n\t'''long function documentation'''\n\treturn ( x + π['x'] )\n"
        expected = "π  =  {'x':  1}\ndef f( x=1 ):\n\treturn ( x + π['x'] )\n"
        self.assertEqual(ASTStripper(True, True).strip(source), expected)
    def test_docstrings_only(self) -> None:
        source = '"module"\n# retained\ndef f(): "long documentation"; return 2 # retained\n'
        result = ASTStripper(False, True).strip(source)
        self.assertEqual(result, '"module"\n# retained\ndef f(): pass; return 2 # retained\n')
    def test_comments_only(self) -> None:
        source = '"module"\ndef f():\n    "documentation"\n    return "# not a comment" # discarded\n'
        result = ASTStripper(True, False).strip(source)
        self.assertIn('"documentation"', result)
        self.assertIn('"# not a comment"', result)
        self.assertNotIn("# discarded", result)
    def test_directives(self) -> None:
        source = "#!/usr/bin/env python3\n# coding: utf-8\n# ruff: noqa\n# fmt: off\n# %%\n# uv: something\n# ordinary\nx = 1 # type: ignore\n"
        self.assertEqual(ASTStripper(True, False).strip(source), source.replace("# ordinary\n", ""))
    def test_literals_that_are_not_docstrings(self) -> None:
        source = 'def f():\n    b"bytes"\ndef g():\n    f"formatted"\nif True:\n    "not a docstring"\n'
        self.assertEqual(ASTStripper(False, True).strip(source), source)
    def test_empty_suites_and_parentheses(self) -> None:
        source = 'async def f():\n    ("documentation" "more")\nclass C: "documentation"\n'
        tree = ast.parse(ASTStripper(False, True).strip(source))
        for node in tree.body:
            self.assertIsInstance(node, (ast.AsyncFunctionDef, ast.ClassDef))
            if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef)):
                self.assertIsNone(ast.get_docstring(node))
                self.assertIsInstance(node.body[0], ast.Pass)
    def test_blank_lines_preserve_string_values(self) -> None:
        source = '\n\nx = """first\n\n   \nlast"""\n\n\ny=2\n\n'
        expected = 'x = """first\n\n   \nlast"""\ny=2\n'
        self.assertEqual(remove_blank_lines(source), expected)
    def test_blank_lines_preserve_fstrings(self) -> None:
        source = '\nvalue = f"""start\n\n{1 + 2}\n\nend"""\n\n'
        self.assertEqual(remove_blank_lines(source), source.strip("\n") + "\n")
    def test_explicit_continuation(self) -> None:
        source = "x = 1 \\\n\n+2\n\n"
        result = remove_blank_lines(source)
        self.assertEqual(result, "x = 1 \\\n\n+2\n")
        self.assertEqual(ast.dump(ast.parse(source)), ast.dump(ast.parse(result)))
    def test_encoding_cookie_position(self) -> None:
        source = "\n# coding: latin-1\n\nx = 1\n\n"
        self.assertEqual(remove_blank_lines(source), "\n# coding: latin-1\nx = 1\n")
    def test_crlf(self) -> None:
        source = '# ordinary\r\n\r\ndef f():\r\n    "documentation"\r\n    return 1 # ordinary\r\n\r\n'
        self.assertEqual(ASTStripper(True, True, True).strip(source), "def f():\r\n    return 1\r\n")
    def test_atomic_file_encoding_and_mode(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "encoded.py")
            path.write_bytes('# coding: latin-1\r\n\r\nx = "café" # ordinary\r\n'.encode("latin-1"))
            path.chmod(0o640)
            before = path.stat().st_size
            result = ASTStripper(True, True, True).strip_file(path)
            self.assertIsNone(result.error)
            self.assertEqual(path.read_bytes(), '# coding: latin-1\r\nx = "café"\r\n'.encode("latin-1"))
            self.assertEqual(result.saved, before - path.stat().st_size)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
    def test_invalid_input_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "invalid.py")
            source = b"def broken(\n# comment\n"
            path.write_bytes(source)
            result = ASTStripper(True, True, True).strip_file(path)
            self.assertIsNotNone(result.error)
            self.assertEqual(path.read_bytes(), source)
    def test_backends_share_blank_line_option(self) -> None:
        classes: list[type[ASTStripper]] = [ASTStripper]
        if importlib.util.find_spec("libcst"):
            classes.append(CSTStripper)
        if importlib.util.find_spec("tree_sitter") and importlib.util.find_spec("tree_sitter_python"):
            classes.append(TSStripper)
        source = '"module"\n\n# ordinary\ndef f():\n    "documentation"\n\n    return """a\n\nb"""\n\n'
        expected = '"module"\ndef f():\n    return """a\n\nb"""\n'
        for cls in classes:
            with self.subTest(backend=cls.__name__):
                self.assertEqual(cls(True, True, True).strip(source), expected)
    def test_stdlib_only_cli(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "simple.py")
            path.write_text("\n# ordinary\nx  =  1\n\n")
            proc = subprocess.run(
                [sys.executable, "-S", str(SCRIPT), "-b", "ast", "-c", "--remove-blank-lines"],
                cwd=folder,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(path.read_text(), "x  =  1\n")
            self.assertIn("Total space freed:", proc.stdout)
            self.assertNotIn(str(path), proc.stdout)
    def test_blank_lines_only_cli(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "simple.py")
            path.write_text("\n# keep comment\n\nx=1\n\n")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "-b", "ast", "--remove-blank-lines"],
                cwd=folder,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(path.read_text(), "# keep comment\nx=1\n")
if __name__ == "__main__":
    unittest.main()
