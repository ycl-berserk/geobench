"""The DSL lexer.

Line-oriented: one statement per line. The lexer is deliberately small and
predictable, because the parser's error messages are only useful if the token
positions are exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from geobench.dsl.errors import DSLParseError, Span


class TokenKind(Enum):
    KEYWORD = "keyword"
    IDENT = "ident"
    NUMBER = "number"
    SYMBOL = "symbol"
    PUNCT = "punct"
    END = "end"


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    span: Span

    def is_keyword(self, *words: str) -> bool:
        return self.kind is TokenKind.KEYWORD and self.text in words

    def is_symbol(self, *symbols: str) -> bool:
        return self.kind is TokenKind.SYMBOL and self.text in symbols

    def is_punct(self, *marks: str) -> bool:
        return self.kind is TokenKind.PUNCT and self.text in marks


KEYWORDS = frozenset(
    {
        "点",
        "线段",
        "直线",
        "圆",
        "过",
        "以",
        "为圆心",
        "半径",
        "中点",
        "垂足",
        "垂线",
        "平行线",
        "交点",
        "另一交点",
        "上",
        "与",
        "共线",
        "共圆",
        "垂直",
        "平行",
        "相等",
        "的",
        "内心",
        "外心",
        "垂心",
        "重心",
        "断言",
    }
)

SYMBOLS = frozenset({"⊥", "∥", "∩", "≠", "⊙", "△"})

PUNCT = frozenset({"=", "(", ")", ",", ":"})

# Multi-character keywords must be matched before single ones.
_KEYWORD_ORDER = sorted(KEYWORDS, key=len, reverse=True)


@dataclass(frozen=True)
class Line:
    """One source line, split into tokens."""

    number: int
    tokens: list[Token]
    text: str


def _span(line: int, col: int, length: int = 1) -> Span:
    return Span(line=line, col=col, length=length)


def _is_cjk(char: str) -> bool:
    """Is this a Chinese character (or other CJK ideograph)?"""
    return "一" <= char <= "鿿"


def tokenize_line(text: str, line_number: int) -> list[Token]:
    """Split one line into tokens."""
    tokens: list[Token] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char == "#":
            break  # comment to end of line
        # A symbol may be attached to an identifier, e.g. "⊙O" or "P_1".
        if char in SYMBOLS:
            tokens.append(Token(TokenKind.SYMBOL, char, _span(line_number, index + 1)))
            index += 1
            continue
        if char in PUNCT:
            tokens.append(Token(TokenKind.PUNCT, char, _span(line_number, index + 1)))
            index += 1
            continue
        if char.isdigit() or (char == "-" and index + 1 < length and text[index + 1].isdigit()):
            start = index
            if char == "-":
                index += 1
            while index < length and text[index].isdigit():
                index += 1
            # A fraction such as 1/2.
            if index < length and text[index] == "/" and index + 1 < length and text[index + 1].isdigit():
                index += 1
                while index < length and text[index].isdigit():
                    index += 1
            tokens.append(
                Token(TokenKind.NUMBER, text[start:index], _span(line_number, start + 1, index - start))
            )
            continue
        # Chinese characters must be matched against the keywords *before* the
        # identifier branch: Python reports them as alphabetic, so "点" would
        # otherwise be lexed as a name.
        if _is_cjk(char):
            matched = None
            for keyword in _KEYWORD_ORDER:
                if text.startswith(keyword, index):
                    matched = keyword
                    break
            if matched is not None:
                index += len(matched)
                tokens.append(
                    Token(TokenKind.KEYWORD, matched, _span(line_number, index - len(matched) + 1, len(matched)))
                )
                continue
            index += 1
            tokens.append(Token(TokenKind.IDENT, char, _span(line_number, index)))
            continue
        if char.isalpha() or char == "_":
            start = index
            while index < length and (text[index].isalnum() or text[index] == "_"):
                index += 1
            word = text[start:index]
            tokens.append(Token(TokenKind.IDENT, word, _span(line_number, start + 1, index - start)))
            continue
        # Chinese characters: keywords or object names.
        start = index
        matched = None
        for keyword in _KEYWORD_ORDER:
            if text.startswith(keyword, index):
                matched = keyword
                break
        if matched is not None:
            index += len(matched)
            tokens.append(
                Token(TokenKind.KEYWORD, matched, _span(line_number, start + 1, len(matched)))
            )
            continue
        # A single Chinese character that is not a keyword is an object name.
        index += 1
        tokens.append(Token(TokenKind.IDENT, text[start:index], _span(line_number, start + 1)))
        continue
    return tokens

def tokenize(source: str) -> list[Line]:
    """Tokenize the whole source into lines of tokens."""
    lines: list[Line] = []
    for number, text in enumerate(source.splitlines(), start=1):
        lines.append(Line(number=number, tokens=tokenize_line(text, number), text=text))
    return lines


def expect_keyword(token: Token, words: tuple[str, ...], source: str) -> None:
    if not token.is_keyword(*words):
        raise DSLParseError(
            token.span,
            f"这里应该出现 {'/'.join(words)}，实际是 {token.text!r}",
            source,
        )
