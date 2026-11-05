"""The DSL's errors.

Every parse failure must be *actionable*: an agent that mistypes a clause
needs to know where, so it can fix and retry. A vague error costs a whole
round trip.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """A range in the source text, 1-based line and column."""

    line: int
    col: int
    length: int = 1

    def describe(self) -> str:
        return f"第 {self.line} 行第 {self.col} 列"


class DSLParseError(Exception):
    """The DSL could not be parsed, or parsed into something undefined."""

    def __init__(self, span: Span, message: str, source: str = "") -> None:
        self.span = span
        self.message = message
        self.source = source
        excerpt = ""
        if source:
            lines = source.splitlines()
            if 0 < span.line <= len(lines):
                text = lines[span.line - 1]
                start = max(0, span.col - 1)
                excerpt = text[start : start + max(span.length, 1)]
        detail = f"{span.describe()}：{message}"
        if excerpt:
            detail += f"\n    {excerpt}"
        super().__init__(detail)
