from __future__ import annotations

import ast
import codecs
import io
import os
import re
import shutil
import tempfile
import textwrap
import tokenize
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

try:
    import tree_sitter_python as _tsp
    from tree_sitter import Language as _Language
    from tree_sitter import Parser as _Parser
except ImportError:  # pragma: no cover
    _tsp = _Language = _Parser = None
try:
    import libcst as cst
except ImportError:  # pragma: no cover
    cst = None
_Edit = tuple[int, int, bytes]
_NL = re.compile(rb"\r\n|\r|\n")
_NL_STR = re.compile(r"\r\n|\r|\n")
_DIRECTIVE_RE = re.compile(
    r"#\s*(?:type\s*:|fmt\s*:|isort\s*:|yapf\s*:|pragma\b|pyre-|"
    r"mypy\b|pylint\b|ruff\b|pyright\b|pytype\b|flake8\b|noqa\b|nosec\b)",
    re.IGNORECASE,
)
_COOKIE_RE = re.compile(r"#.*?coding[:=][ \t]*[-\w.]+")
_DEF_TYPES = ("function_definition", "class_definition")
_LINE_START_TOKENS = (None, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
_BLOCK_PREFIX = {
    "else": "if 1:\n pass\n",
    "elif": "if 1:\n pass\n",
    "except": "try:\n pass\n",
    "finally": "try:\n pass\n",
}


@dataclass
class StripFileResult:
    path: Path
    modified: bool
    valid: bool
    error: str | None = None
    bytes_reduced: int = 0


class _BaseStripper(ABC):
    name = ""

    def __init__(
        self,
        strip_comments: bool = True,
        strip_docstrings: bool = True,
        preserve_shebangs: bool = False,
        preserve_module_docstring: bool = False,
        preserve_directives: bool = True,
        validate: bool = True,
        preserve_commented_code: bool = True,
    ) -> None:
        self.strip_comments = strip_comments
        self.strip_docstrings = strip_docstrings
        self.preserve_shebangs = preserve_shebangs
        self.preserve_module_docstring = preserve_module_docstring
        self.preserve_directives = preserve_directives
        self.validate = validate
        self.preserve_commented_code = preserve_commented_code
        self._setup()

    def _setup(self) -> None:
        pass

    @abstractmethod
    def _strip_unchecked(self, source: str) -> str: ...
    def strip(self, source: str) -> str:
        try:
            result = self._strip_unchecked(source)
        except Exception:
            return source
        if self.validate and not self._is_valid(result):
            return source
        return result

    def strip_file(
        self,
        path: str | os.PathLike[str],
        *,
        encoding: str | None = None,
    ) -> StripFileResult:
        p = Path(path)

        def fail(exc: BaseException | str) -> StripFileResult:
            msg = exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
            return StripFileResult(path=p, modified=False, valid=False, error=msg)

        try:
            raw = p.read_bytes()
            enc = encoding or tokenize.detect_encoding(io.BytesIO(raw).readline)[0]
            if enc.lower().replace("_", "-") in ("utf-8", "utf8") and raw.startswith(codecs.BOM_UTF8):
                enc = "utf-8-sig"
            original = raw.decode(enc)
            stripped = self._strip_unchecked(original)
        except Exception as e:
            return fail(e)
        if self.validate:
            err = self._parse_error(stripped)
            if err:
                return fail(err)
        if stripped == original:
            return StripFileResult(path=p, modified=False, valid=True)
        try:
            new_raw = stripped.encode(enc)
            self._atomic_write(p, new_raw)
        except Exception as e:
            return fail(e)
        return StripFileResult(path=p, modified=True, valid=True, bytes_reduced=len(raw) - len(new_raw))

    def _commented_code(self, source: str) -> frozenset[str]:
        if not (self.strip_comments and self.preserve_commented_code):
            return frozenset()
        runs: list[list[str]] = []
        last_row = -2
        prev = None
        for tok in tokenize.generate_tokens(io.StringIO(source, newline="").readline):
            if tok.type == tokenize.COMMENT and prev in _LINE_START_TOKENS:
                row = tok.start[0]
                if runs and row == last_row + 1:
                    runs[-1].append(tok.string.rstrip())
                else:
                    runs.append([tok.string.rstrip()])
                last_row = row
            prev = tok.type
        found: set[str] = set()
        for run in runs:
            bodies = [c[2:] if c.startswith("# ") else c[1:] for c in run]
            n = len(run)
            i = 0
            while i < n:
                longest = range(min(n, i + 60), i, -1) if n <= 60 else range(i + 1, i, -1)
                for j in longest:
                    if self._looks_like_code(textwrap.dedent("\n".join(bodies[i:j]))):
                        found.update(run[i:j])
                        i = j
                        break
                else:
                    i += 1
        return frozenset(found)

    @staticmethod
    def _looks_like_code(text: str) -> bool:
        body = text.strip("\n").rstrip()
        if not body.strip():
            return False
        head = re.match(r"[A-Za-z_]+", body)
        prefix = _BLOCK_PREFIX.get(head.group(), "") if head else ""
        last = body.splitlines()[-1]
        suffix = ""
        if last.rstrip().endswith(":"):
            suffix = "\n" + " " * (len(last) - len(last.lstrip()) + 4) + "pass"
        elif body.lstrip().startswith("@"):
            suffix = "\ndef _(): pass"
        try:
            tree = ast.parse(prefix + body + suffix)
        except (SyntaxError, ValueError, RecursionError):
            return False
        if prefix:
            return True

        def is_code(stmt: ast.stmt) -> bool:
            if isinstance(stmt, ast.Expr):
                return isinstance(stmt.value, (ast.Call, ast.Await, ast.Yield, ast.YieldFrom))
            if isinstance(stmt, ast.AnnAssign):
                return stmt.value is not None
            return True

        return any(is_code(s) for s in tree.body)

    @staticmethod
    def _parse_error(source: str) -> str | None:
        try:
            ast.parse(source)
        except (SyntaxError, ValueError, RecursionError) as e:
            return f"{type(e).__name__}: {e}"
        return None

    @classmethod
    def _is_valid(cls, source: str) -> bool:
        return cls._parse_error(source) is None

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        target = path.resolve()
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            try:
                shutil.copymode(target, tmp)
            except OSError:
                pass
            os.replace(tmp, target)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise


class _ByteEditStripper(_BaseStripper):
    @abstractmethod
    def _collect_edits(self, src: bytes, code: frozenset[str]) -> list[_Edit]: ...
    def _strip_unchecked(self, source: str) -> str:
        if not (self.strip_comments or self.strip_docstrings):
            return source
        src = source.encode("utf-8")
        edits = self._merge(self._collect_edits(src, self._commented_code(source)))
        return self._apply(src, edits).decode("utf-8")

    @staticmethod
    def _line_start(src: bytes, pos: int) -> int:
        return max(src.rfind(b"\n", 0, pos), src.rfind(b"\r", 0, pos)) + 1

    @staticmethod
    def _line_end(src: bytes, pos: int) -> int:
        m = _NL.search(src, pos)
        return m.end() if m else len(src)

    def _keeps_comment(self, src: bytes, start: int, end: int) -> bool:
        text = src[start:end].decode("utf-8", "replace")
        if self.preserve_shebangs and start == 0 and text.startswith("#!"):
            return True
        if self.preserve_directives and _DIRECTIVE_RE.match(text):
            return True
        return bool(_COOKIE_RE.match(text)) and len(_NL.findall(src, 0, start)) < 2

    def _comment_edit(self, src: bytes, start: int, end: int, code: frozenset[str]) -> _Edit | None:
        if self._keeps_comment(src, start, end):
            return None
        ls = self._line_start(src, start)
        if src[ls:start].strip(b" \t\f") == b"":
            if code and src[start:end].decode("utf-8", "replace").rstrip() in code:
                return None
            return (ls, self._line_end(src, end), b"")
        i = start
        while i > ls and src[i - 1] in (0x20, 0x09, 0x0C):
            i -= 1
        return (i, end, b"")

    def _docstring_edit(self, src: bytes, start: int, end: int, *, replace_with_pass: bool) -> _Edit:
        if replace_with_pass:
            return (start, end, b"pass")
        ls, le = self._line_start(src, start), self._line_end(src, end)
        before, after = src[ls:start], src[end:le]
        tail = after.strip(b" \t\f\r\n")
        if tail.startswith(b";"):
            i = end + after.index(b";") + 1
            while i < len(src) and src[i] in (0x20, 0x09):
                i += 1
            return (start, i, b"")
        if before.strip(b" \t\f") == b"":
            if tail == b"":
                return (ls, le, b"")
            if tail.startswith(b"#"):
                cpos = end + after.index(b"#")
                cend = le
                while cend > cpos and src[cend - 1] in (0x0A, 0x0D):
                    cend -= 1
                if self.strip_comments and not self._keeps_comment(src, cpos, cend):
                    return (ls, le, b"")
        return (start, end, b"")

    @staticmethod
    def _merge(edits: list[_Edit]) -> list[_Edit]:
        out: list[_Edit] = []
        for s, e, r in sorted(edits, key=lambda x: (x[0], x[1])):
            if out and s < out[-1][1]:
                ps, pe, pr = out[-1]
                out[-1] = (ps, max(pe, e), pr or r)
            else:
                out.append((s, e, r))
        return out

    @staticmethod
    def _apply(src: bytes, edits: list[_Edit]) -> bytes:
        parts: list[bytes] = []
        cursor = 0
        for s, e, r in edits:
            parts.append(src[cursor:s])
            parts.append(r)
            cursor = e
        parts.append(src[cursor:])
        return b"".join(parts)


class ASTStripper(_ByteEditStripper):
    name = "ast"

    def _collect_edits(self, src: bytes, code: frozenset[str]) -> list[_Edit]:
        text = src.decode("utf-8")
        char_starts, byte_starts = self._line_tables(text)
        edits: list[_Edit] = []
        if self.strip_comments:

            def to_byte(row: int, col: int) -> int:
                cs = char_starts[row - 1]
                return byte_starts[row - 1] + len(text[cs : cs + col].encode("utf-8"))

            readline = io.StringIO(text, newline="").readline
            for tok in tokenize.generate_tokens(readline):
                if tok.type == tokenize.COMMENT:
                    e = self._comment_edit(src, to_byte(*tok.start), to_byte(*tok.end), code)
                    if e:
                        edits.append(e)
        if self.strip_docstrings:
            for node in ast.walk(ast.parse(text)):
                if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                is_module = isinstance(node, ast.Module)
                if is_module and self.preserve_module_docstring:
                    continue
                first = node.body[0] if node.body else None
                if not (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    continue
                start = byte_starts[first.lineno - 1] + first.col_offset
                end = byte_starts[first.end_lineno - 1] + first.end_col_offset
                sole = len(node.body) == 1 and not is_module
                edits.append(self._docstring_edit(src, start, end, replace_with_pass=sole))
        return edits

    @staticmethod
    def _line_tables(text: str) -> tuple[list[int], list[int]]:
        chars, bytes_ = [0], [0]
        pos = nbytes = 0
        for m in _NL_STR.finditer(text):
            nbytes += len(text[pos : m.end()].encode("utf-8"))
            pos = m.end()
            chars.append(pos)
            bytes_.append(nbytes)
        return chars, bytes_


class TSStripper(_ByteEditStripper):
    name = "tree-sitter"

    def _setup(self) -> None:
        if _tsp is None or _Parser is None:
            raise ImportError("TSStripper needs `tree-sitter` and `tree-sitter-python`")
        lang = _Language(_tsp.language())
        try:
            self._parser = _Parser(lang)
        except TypeError:
            self._parser = _Parser()
            try:
                self._parser.language = lang
            except (AttributeError, ValueError):
                self._parser.set_language(lang)

    def _collect_edits(self, src: bytes, code: frozenset[str]) -> list[_Edit]:
        root = self._parser.parse(src).root_node
        if root.has_error and not self.validate:
            raise ValueError("tree-sitter reported syntax errors")
        edits: list[_Edit] = []
        stack = [root]
        while stack:
            node = stack.pop()
            kind = node.type
            if kind == "comment":
                if self.strip_comments:
                    e = self._comment_edit(src, node.start_byte, node.end_byte, code)
                    if e:
                        edits.append(e)
                continue
            if self.strip_docstrings:
                if kind == "module":
                    if not self.preserve_module_docstring:
                        self._docstring_of(node, src, edits, is_module=True)
                elif kind in _DEF_TYPES:
                    body = node.child_by_field_name("body")
                    if body is not None:
                        self._docstring_of(body, src, edits, is_module=False)
            stack.extend(node.named_children)
        return edits

    def _docstring_of(self, container, src: bytes, edits: list[_Edit], *, is_module: bool) -> None:
        if container.type in ("module", "block"):
            stmts = [c for c in container.named_children if c.type != "comment"]
        else:
            stmts = [container]
        if not stmts or not self._is_docstring(stmts[0], src):
            return
        sole = len(stmts) == 1 and not is_module
        first = stmts[0]
        edits.append(self._docstring_edit(src, first.start_byte, first.end_byte, replace_with_pass=sole))

    @staticmethod
    def _is_docstring(stmt, src: bytes) -> bool:
        if stmt.type != "expression_statement" or len(stmt.named_children) != 1:
            return False
        lit = stmt.named_children[0]
        if lit.type == "string":
            parts = [lit]
        elif lit.type == "concatenated_string":
            parts = [c for c in lit.named_children if c.type == "string"]
        else:
            return False
        for part in parts:
            prefix = re.match(rb"[A-Za-z]*", src[part.start_byte : part.end_byte]).group().lower()
            if any(ch in b"bft" for ch in prefix):
                return False
        return bool(parts)


_CSTBase = cst.CSTTransformer if cst is not None else object


class _DocstringRemover(_CSTBase):
    def __init__(self, strip_module: bool) -> None:
        super().__init__()
        self._strip_module = strip_module

    @classmethod
    def _is_str(cls, node) -> bool:
        if isinstance(node, cst.SimpleString):
            return "b" not in node.prefix.lower()
        if isinstance(node, cst.ConcatenatedString):
            return cls._is_str(node.left) and cls._is_str(node.right)
        return False

    @classmethod
    def _is_doc(cls, small) -> bool:
        return isinstance(small, cst.Expr) and cls._is_str(small.value)

    def _lines(self, stmts: Sequence, *, is_module: bool) -> list | None:
        first = stmts[0] if stmts else None
        if not isinstance(first, cst.SimpleStatementLine) or not first.body or not self._is_doc(first.body[0]):
            return None
        rest_small = list(first.body[1:])
        if rest_small:
            return [first.with_changes(body=rest_small), *stmts[1:]]
        rest = list(stmts[1:])
        if not rest:
            return [] if is_module else [first.with_changes(body=[cst.Pass()])]
        carried = [ln for ln in first.leading_lines if ln.comment is not None]
        head = rest[0].with_changes(leading_lines=[*carried, *rest[0].leading_lines])
        return [head, *rest[1:]]

    def _suite(self, small: Sequence) -> list | None:
        if not small or not self._is_doc(small[0]):
            return None
        return list(small[1:]) or [cst.Pass()]

    def _def(self, updated):
        body = updated.body
        if isinstance(body, cst.IndentedBlock):
            new = self._lines(body.body, is_module=False)
        elif isinstance(body, cst.SimpleStatementSuite):
            new = self._suite(body.body)
        else:
            return updated
        return updated if new is None else updated.with_changes(body=body.with_changes(body=new))

    def leave_FunctionDef(self, original, updated):
        return self._def(updated)

    def leave_ClassDef(self, original, updated):
        return self._def(updated)

    def leave_Module(self, original, updated):
        if not self._strip_module:
            return updated
        new = self._lines(updated.body, is_module=True)
        return updated if new is None else updated.with_changes(body=new)


class _CommentRemover(_CSTBase):
    def __init__(self, keep: Callable[[str], bool], code: frozenset[str]) -> None:
        super().__init__()
        self._keep = keep
        self._code = code

    def leave_EmptyLine(self, original, updated):
        if original.comment is None:
            return updated
        if self._keep(original.comment.value) or original.comment.value.rstrip() in self._code:
            return updated
        return cst.RemoveFromParent()

    def leave_TrailingWhitespace(self, original, updated):
        if original.comment is None or self._keep(original.comment.value):
            return updated
        return updated.with_changes(comment=None, whitespace=cst.SimpleWhitespace(""))


class CSTStripper(_BaseStripper):
    name = "libcst"

    def _setup(self) -> None:
        if cst is None:
            raise ImportError("CSTStripper needs `libcst`")

    def _keep_predicate(self, source: str) -> Callable[[str], bool]:
        protected: set[str] = set()
        for i, line in enumerate(source.split("\n", 2)[:2]):
            s = line.strip()
            if i == 0 and self.preserve_shebangs and s.startswith("#!"):
                protected.add(s)
            elif _COOKIE_RE.match(s):
                protected.add(s)

        def keep(value: str) -> bool:
            v = value.rstrip()
            return v in protected or (self.preserve_directives and bool(_DIRECTIVE_RE.match(v)))

        return keep

    def _strip_unchecked(self, source: str) -> str:
        if not (self.strip_comments or self.strip_docstrings):
            return source
        module = cst.parse_module(source)
        if self.strip_docstrings:
            module = module.visit(_DocstringRemover(not self.preserve_module_docstring))
        if self.strip_comments:
            module = module.visit(_CommentRemover(self._keep_predicate(source), self._commented_code(source)))
        return module.code
