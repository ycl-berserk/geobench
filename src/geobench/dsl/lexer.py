"""The DSL lexer.

Line-oriented: one statement per line. The lexer is deliberately small and
predictable, because the parser's error messages are only useful if the token
positions are exact.

Two things here are worth knowing.

**Chinese words are lexed whole.** A command name is a Chinese word
(``中点``, ``外接圆``), so ``中点(A,B)`` must reach the parser as one
identifier, not as two characters. A run of Chinese characters is
therefore lexed as a single token.

**Only the statement heads are keywords.** ``点`` and ``断言`` introduce a
statement; everything else is a *name*, resolved against the command
table (:mod:`geobench.commands`). That is what lets a command be called
by its Chinese name or by GeoGebra's English one without the lexer
knowing about either.
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


#: The statement heads. Everything else is a name.
KEYWORDS = frozenset({"点", "断言"})

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
            # A decimal such as 2.5.
            if (
                index < length
                and text[index] == "."
                and index + 1 < length
                and text[index + 1].isdigit()
            ):
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
        if _is_cjk(char):
            # A run of Chinese characters is one word: a command name, an
            # object name or a selector.
            start = index
            while index < length and _is_cjk(text[index]):
                index += 1
            run = text[start:index]
            head = _statement_head(run)
            if head is not None:
                tokens.append(
                    Token(TokenKind.KEYWORD, head, _span(line_number, start + 1, len(head)))
                )
                rest = run[len(head) :]
                tokens.append(
                    Token(
                        TokenKind.IDENT,
                        rest,
                        _span(line_number, start + len(head) + 1, len(rest)),
                    )
                )
            elif run in KEYWORDS:
                tokens.append(
                    Token(TokenKind.KEYWORD, run, _span(line_number, start + 1, len(run)))
                )
            else:
                tokens.append(
                    Token(TokenKind.IDENT, run, _span(line_number, start + 1, len(run)))
                )
            continue
        if char.isalpha() or char == "_":
            start = index
            while index < length and (text[index].isalnum() or text[index] == "_"):
                index += 1
            word = text[start:index]
            tokens.append(Token(TokenKind.IDENT, word, _span(line_number, start + 1, index - start)))
            continue
        # Anything else: keep it as a symbol so that the parser can say
        # where it did not expect it, rather than dropping it silently.
        tokens.append(Token(TokenKind.SYMBOL, char, _span(line_number, index + 1)))
        index += 1
    return tokens


def _statement_head(run: str) -> str | None:
    """The statement keyword a Chinese run begins with, if any.

    ``断言共线(A,B)`` is one run; the head is ``断言`` and the rest is
    the command name. Splitting here means the author need not put a
    space between them.
    """
    for keyword in _KEYWORD_ORDER:
        if run.startswith(keyword) and len(run) > len(keyword):
            return keyword
    return None

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
