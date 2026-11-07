"""The exactness invariant, enforced mechanically.

Floating point may only appear at the render boundary and in the numeric
path -- the fast, approximate path that draws the screen and never
produces a verdict (decision D18). This test walks the AST of every
kernel module and fails on any float literal that is not inside an
explicitly allowed module.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "geobench"

ALLOWED_FUNCTIONS = {"to_float", "to_floats"}

#: The modules where floating point is allowed, and why.
#:
#: Each entry is a deliberate exception with a reason. The list is
#: short on purpose: every name in it is a place where an approximation
#: could leak into a verdict, so each one is a thing to keep an eye on.
ALLOWED_MODULES = {
    "render": "the renderer draws in pixels",
    "style": "the style preset carries point sizes and line widths",
    "numeric": "the numeric path is the display path; it may never produce "
    "a verdict, which tests/contract asserts",
}


def _is_allowed_module(path: Path) -> bool:
    return path.stem in ALLOWED_MODULES


def find_float_literals(source: str, allowed_functions: frozenset[str] = frozenset()) -> list[tuple[int, float]]:
    """Return (line, value) for every float literal outside allowed functions."""
    tree = ast.parse(source)
    violations: list[tuple[int, float]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.allowed = False

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            previous = self.allowed
            self.allowed = previous or node.name in allowed_functions
            self.generic_visit(node)
            self.allowed = previous

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.visit_FunctionDef(node)  # type: ignore[arg-type]

        def visit_Constant(self, node: ast.Constant) -> None:
            if isinstance(node.value, float) and not self.allowed:
                violations.append((node.lineno, node.value))

    Visitor().visit(tree)
    return violations


def test_scanner_detects_a_violation() -> None:
    assert find_float_literals("x = 0.5\n") == [(1, 0.5)]
    assert find_float_literals("def to_float(x):\n    return 0.5\n", frozenset({"to_float"})) == []


def test_kernel_contains_no_floating_point_literals() -> None:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if _is_allowed_module(path):
            continue
        source = path.read_text(encoding="utf-8")
        for line, value in find_float_literals(source, frozenset(ALLOWED_FUNCTIONS)):
            violations.append(f"{path.relative_to(SRC)}:{line}: float literal {value}")
    assert not violations, "floating point literals in the kernel:\n" + "\n".join(violations)
