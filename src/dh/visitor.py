from __future__ import annotations

from typing import Any, Union

NodeType = Union[list, str, int, bool, dict]


class Visitor:
    def visit(self, node: NodeType) -> Any:
        mro = node.__mro__ if isinstance(node, type) else type(node).__mro__
        for cls in mro:
            method_name = f"visit_{cls.__name__}"
            meth = getattr(self, method_name, None)
            if meth:
                return meth(node)
        msg = f"No visitation method visit_{type(node).__name__}"
        raise NotImplementedError(msg)


class JsonEncoder(Visitor):
    def __init__(self) -> None:
        self.indent_level: int = 0
        self.indent_str: str = "  "

    def _escape_str(self, s: str) -> str:
        escape_map = {"\\": "\\\\", '"': '\\"'}
        trans_table = str.maketrans(escape_map)
        return '"' + s.translate(trans_table) + '"'

    def _get_indent(self) -> str:
        return self.indent_str * self.indent_level

    def visit_list(self, node: list) -> str:
        self.indent_level += 1
        indent_after_bracket = self._get_indent()
        items_str = f",\n{indent_after_bracket}".join(self.visit(item) for item in node)
        self.indent_level -= 1
        indent_before_bracket = self._get_indent()
        return f"[\n{indent_after_bracket}{items_str}\n{indent_before_bracket}]"

    def visit_str(self, node: str) -> str:
        return self._escape_str(node)

    def visit_int(self, node: int) -> str:
        return str(node)

    def visit_bool(self, node: bool) -> str:
        return "true" if node else "false"

    def visit_dict(self, node: dict) -> str:
        self.indent_level += 1
        indent_after_brace = self._get_indent()
        items_str = f",\n{indent_after_brace}".join(
            f"{self._escape_str(key)}: {self.visit(value)}"
            for key, value in sorted(node.items())
        )
        self.indent_level -= 1
        indent_before_brace = self._get_indent()
        return f"{{\n{indent_after_brace}{items_str}\n{indent_before_brace}}}"
