"""The DSL parser: text in, construction graph out.

A recursive-descent parser over the line-oriented DSL of
``docs/dsl-spec.md``. It is deliberately strict: an unrecognised clause is an
error with an exact position, never a guess. The whole point of the DSL is
that it can be checked.

The syntax is **function-call**, with GeoGebra's Chinese command names
(decision D17)::

    点 A(0,0) B(4,0) C(1,3)
    △ABC
    M = 中点(A,B)
    O = 外接圆(A,B,C)
    P = 交点(AD,⊙O,另一交点)
    断言 共线(M,A,B)
    断言 相等(AB,AC)

A teacher who types ``Midpoint(A,B)`` in GeoGebra types exactly the same
thing here, in English, and it means the same thing: the English command
name is accepted everywhere the Chinese one is (GeoGebra's own input bar
accepts English in every language).

**Overloading is resolved by the arguments.** ``交点`` is line-line,
line-circle or circle-circle; ``圆`` is centre-radius or
centre-through-point. The parser picks the command whose parameters fit
what was actually written, and complains when none does.

The parser builds a figure directly. It never calls a model and never makes
a network request -- that is the difference between the DSL layer and the
text2graph layer above it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import sympy as sp
from sympy import Expr

from geobench.commands import (
    COMMANDS,
    JUDGEMENT,
    MEASUREMENT,
    SELECTORS,
    CommandSpec,
    by_id,
    lookup_all,
)
from geobench.dsl.errors import DSLParseError, Span
from geobench.dsl.lexer import Line, Token, TokenKind, tokenize
from geobench.errors import StateError
from geobench.evaluate import evaluate_figure
from geobench.judges import JudgeContext, JudgeRegistry
from geobench.model import (
    ARC,
    CIRCLE,
    FREE,
    LINE,
    NUMBER,
    POINT,
    POLYGON,
    POLYLINE,
    RAY,
    SECTOR,
    SEGMENT,
    TEXT,
    Figure,
    Node,
    Relation,
)
from geobench.operators import OpContext
from geobench.operators import register_builtins as _register_builtins
from geobench.registry import OperatorRegistry, OpSpec
from geobench.solve import Condition, solve
from geobench.style import (
    DEFAULT,
    LABEL_DIRECTIONS,
    LINE_WIDTHS,
    POINT_SIZES,
    resolve_color,
)

# -- object table ----------------------------------------------------------

#: The functions a coordinate may use.  Only ``sqrt``: a coordinate is a
#: number, and a number that needs a logarithm is not one a figure has.
_VALUE_FUNCTIONS = {"sqrt": sp.sqrt}


@dataclass(frozen=True)
class _Pending:
    """A constraint as written, before the figure is evaluated.

    A judgement cannot produce its expression until the figure has been
    evaluated (a line's coefficients live in the cache), and a
    constraint may name an object that comes later in the script.  So
    the pieces are kept and turned into an expression at the end.
    """

    label: str
    command: Token
    args: list[Arg]
    right: Expr | None = None
    right_call: tuple[Token, list[Arg]] | None = None


@dataclass
class Ref:
    """A named object in the DSL's scope."""

    name: str
    kind: str  # "point" | "segment" | "line" | "circle"
    node_id: str
    endpoints: tuple[str, ...] = ()


@dataclass
class Scope:
    """The names a DSL script has introduced so far."""

    objects: dict[str, Ref] = field(default_factory=dict)

    def point(self, name: str, source: str, span: Span) -> Ref:
        ref = self.objects.get(name)
        if ref is None or ref.kind != "point":
            raise DSLParseError(span, f"未定义的点 {name!r}", source)
        return ref

    def pair(self, name: str, source: str, span: Span) -> tuple[str, str]:
        """The two endpoints of a two-letter name such as ``BC``.

        A two-letter name is the segment between two points -- the way a
        competition paper writes it -- unless the script has declared a
        segment by that name, in which case the declared one wins.
        """
        ref = self.objects.get(name)
        if ref is not None and len(ref.endpoints) == 2:
            return ref.endpoints
        if len(name) == 2 and name.isalpha():
            first = self.objects.get(name[0])
            second = self.objects.get(name[1])
            if first is not None and first.kind == "point":
                if second is None or second.kind != "point":
                    raise DSLParseError(span, f"未定义的点 {name[1]!r}", source)
                return (first.node_id, second.node_id)
        raise DSLParseError(span, f"无法解析对象 {name!r} 的两个端点", source)

    def circle(self, name: str, source: str, span: Span) -> str:
        ref = self.objects.get(name)
        if ref is None or ref.kind != "circle":
            raise DSLParseError(span, f"未定义的圆 {name!r}", source)
        return ref.node_id


@dataclass
class Arg:
    """One argument of a command call."""

    kind: str  # "point" | "segment" | "line" | "circle" | "number" | "selector"
    node_id: str = ""
    value: str = ""
    endpoints: tuple[str, ...] = ()
    name: str = ""


#: The kinds an operator argument may ask for, and the argument kinds
#: that satisfy it.
_TYPE_FITS: dict[str, frozenset[str]] = {
    "point": frozenset({"point"}),
    "line": frozenset({"line", "segment"}),
    "segment": frozenset({"segment"}),
    "circle": frozenset({"circle"}),
    "polygon": frozenset({"polygon"}),
    "scalar": frozenset({"number"}),
    # A selector may be written as a Chinese word (第一交点) or as the
    # index it is: 交点(直线, 圆, 0).  GeoGebra counts from 1 and this
    # language counts from 0, so the *number* has to be accepted here --
    # and it is, since T034 needed to write imported figures.
    "selector": frozenset({"selector", "number"}),
}


# -- parser ----------------------------------------------------------------


class Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.lines = tokenize(source)
        self.figure = Figure(id="fig_dsl")
        self.scope = Scope()
        self._auto_names: dict[str, int] = {}
        #: The conditions the figure has to satisfy, in the order written.
        #: They are solved *after* the whole figure is built, because a
        #: constraint may name anything that comes later in the script.
        self.constraints: list[_Pending] = []

    # -- token helpers ----------------------------------------------------

    def _peek(self, tokens: list[Token], index: int) -> Token | None:
        if index < len(tokens):
            return tokens[index]
        return None

    def _fail(self, span: Span, message: str) -> DSLParseError:
        return DSLParseError(span, message, self.source)

    # -- statements -------------------------------------------------------

    def parse(self) -> Figure:
        for line in self.lines:
            if not line.tokens:
                continue
            self._parse_line(line)
        self._solve_constraints()
        return self.figure

    def _parse_line(self, line: Line) -> None:
        tokens = line.tokens
        head = tokens[0]
        if head.is_keyword("点") or head.text == "Point":
            self._parse_points(tokens, line)
            return
        if head.text in {"数", "Number"}:
            self._parse_number(tokens)
            return
        if head.text in {"文本", "Text"}:
            self._parse_text(tokens)
            return
        if head.is_keyword("断言"):
            self._parse_assertion(tokens)
            return
        if head.is_keyword("约束"):
            self._parse_constraint(tokens)
            return
        if head.text in {"\u9690\u85cf", "Hide"}:
            self._parse_attribute(tokens, hidden=True)
            return
        if head.text in {"\u8f85\u52a9", "Auxiliary"}:
            self._parse_attribute(tokens, hidden=False)
            return
        if head.text in {"\u9690\u85cf\u6807\u7b7e", "HideLabel"}:
            self._parse_label_visibility(tokens, False)
            return
        if head.text in {"\u663e\u793a\u6807\u7b7e", "ShowLabel"}:
            self._parse_label_visibility(tokens, True)
            return
        if head.text in {"\u989c\u8272", "Color"}:
            self._parse_appearance(tokens, "color")
            return
        if head.text in {"\u7ebf\u5bbd", "LineWidth"}:
            self._parse_appearance(tokens, "width")
            return
        if head.is_keyword("\u70b9\u5927\u5c0f") or head.text == "PointSize":
            self._parse_appearance(tokens, "size")
            return
        if head.text in {"\u6807\u7b7e\u4f4d\u7f6e", "LabelPosition"}:
            self._parse_appearance(tokens, "label_pos")
            return
        if head.is_symbol("△"):
            self._parse_triangle(tokens)
            return
        if len(tokens) >= 3 and tokens[1].is_punct("="):
            self._parse_assignment(tokens[0], tokens[2:])
            return
        if len(tokens) >= 2 and tokens[1].is_punct("("):
            # A bare call, as GeoGebra allows: it names the result itself.
            command_token = head
            args = self._parse_call(command_token, tokens)
            command = self._resolve(command_token.text, args, command_token.span, judgement=None)
            if command.kind == JUDGEMENT:
                self._add_relation(command, args)
                return
            self._build(
                command_token.text,
                args,
                self._auto_name(command),
                command_token.span,
            )
            return
        raise self._fail(head.span, "这一行看不懂：应该是一个赋值、一个断言或一条点声明")

    # -- 点 A(0,0) B(4,0) -------------------------------------------------

    def _parse_points(self, tokens: list[Token], line: Line) -> None:
        index = 1
        while index < len(tokens):
            name_token = tokens[index]
            if name_token.kind is not TokenKind.IDENT:
                raise self._fail(name_token.span, "这里应该是一个点的名字")
            index += 1
            if index >= len(tokens) or not tokens[index].is_punct("("):
                raise self._fail(tokens[index - 1].span, "点的名字后面应该跟坐标")
            index += 1
            x, index = self._expect_value(tokens, index, line)
            if index >= len(tokens) or not tokens[index].is_punct(","):
                raise self._fail(tokens[index - 1].span, "两个坐标之间应该有逗号")
            index += 1
            y, index = self._expect_value(tokens, index, line)
            if index >= len(tokens) or not tokens[index].is_punct(")"):
                raise self._fail(tokens[index - 1].span, "坐标后面应该有右括号")
            index += 1
            self._add_free_point(name_token.text, x, y, name_token.span)

    # -- an exact coordinate ------------------------------------------------

    def _expect_value(self, tokens: list[Token], index: int, line: Line) -> tuple[str, int]:
        """One coordinate, exactly.

        ``3``, ``-3``, ``1/2``, ``2*sqrt(3)``, ``(1+sqrt(5))/2`` -- any
        number that can be written exactly.  A decimal is read as the
        rational it is (``2.5`` is ``5/2``), so the kernel never sees a
        float.

        This is not a calculator: the only function is ``sqrt``, and
        there are no variables.  A coordinate is a number, not a program
        -- which is also why the error says so when somebody writes
        ``sqrt(a)``.
        """
        had = index
        value, index = self._value_sum(tokens, index, line)
        if value.free_symbols:
            raise self._fail(
                tokens[had].span,
                "坐标必须是数：可以用 sqrt(3)、1/2 这样的精确写法，但不能带字母",
            )
        return str(value), index

    def _value_sum(self, tokens: list[Token], index: int, line: Line) -> tuple[Expr, int]:
        value, index = self._value_product(tokens, index, line)
        while index < len(tokens):
            token = tokens[index]
            if token.kind is TokenKind.SYMBOL and token.text in "+-":
                right, index = self._value_product(tokens, index + 1, line)
                value = value + right if token.text == "+" else value - right
            elif token.kind is TokenKind.NUMBER and token.text.startswith("-"):
                # The lexer folds a minus into the number that follows it,
                # so "2*sqrt(3)-1" arrives as two numbers with no operator
                # between them.
                value = value + self._number(token)
                index += 1
            else:
                break
        return value, index

    def _value_product(self, tokens: list[Token], index: int, line: Line) -> tuple[Expr, int]:
        value, index = self._value_factor(tokens, index, line)
        while index < len(tokens):
            token = tokens[index]
            if token.kind is not TokenKind.SYMBOL or token.text not in "*/":
                break
            right, index = self._value_factor(tokens, index + 1, line)
            if token.text == "*":
                value = value * right
            else:
                if right == 0:
                    raise self._fail(token.span, "除以零")
                value = value / right
        return value, index

    def _value_factor(self, tokens: list[Token], index: int, line: Line) -> tuple[Expr, int]:
        if index >= len(tokens):
            raise self._fail(Span(line=line.number, col=1), "坐标没写完")
        token = tokens[index]
        if token.kind is TokenKind.NUMBER:
            return self._number(token), index + 1
        if token.kind is TokenKind.SYMBOL and token.text == "-":
            value, index = self._value_factor(tokens, index + 1, line)
            return -value, index
        if token.kind is TokenKind.SYMBOL and token.text == "+":
            return self._value_factor(tokens, index + 1, line)
        if token.kind is TokenKind.IDENT and token.text in _VALUE_FUNCTIONS:
            if index + 1 >= len(tokens) or not tokens[index + 1].is_punct("("):
                raise self._fail(token.span, f"{token.text} 后面应该跟括号")
            value, index = self._value_sum(tokens, index + 2, line)
            if index >= len(tokens) or not tokens[index].is_punct(")"):
                raise self._fail(token.span, "括号没关上")
            return _VALUE_FUNCTIONS[token.text](value), index + 1
        if token.is_punct("("):
            value, index = self._value_sum(tokens, index + 1, line)
            if index >= len(tokens) or not tokens[index].is_punct(")"):
                raise self._fail(token.span, "括号没关上")
            return value, index + 1
        if token.kind is TokenKind.IDENT:
            if index + 1 < len(tokens) and tokens[index + 1].is_punct("("):
                raise self._fail(token.span, f"坐标里只有 sqrt，没有 {token.text}")
            raise self._fail(
                token.span,
                f"{token.text!r} 不是数 —— 坐标里不能有字母，"
                "只能用数字、sqrt(3)、1/2 这样的写法",
            )
        raise self._fail(token.span, "这里应该是一个数（可以用 sqrt(3) 这样的写法）")

    def _number(self, token: Token) -> Expr:
        """A number token as the exact number it is."""
        try:
            return sp.Rational(token.text)
        except (TypeError, ValueError, ZeroDivisionError):
            raise self._fail(token.span, f"{token.text!r} 不是一个数") from None

    def _add_free_point(self, name: str, x: str, y: str, span: Span) -> None:
        node = Node(
            id=name,
            kind=POINT,
            role=FREE,
            coords=(f"x_{name}", f"y_{name}"),
            placement=(x, y),
        )
        self._install(node, span)
        self.scope.objects[name] = Ref(name=name, kind="point", node_id=name)

    # -- △ABC -------------------------------------------------------------

    def _parse_triangle(self, tokens: list[Token]) -> None:
        if len(tokens) != 2 or tokens[1].kind is not TokenKind.IDENT:
            raise self._fail(tokens[0].span, "△ 后面应该是三个顶点，如 △ABC")
        name = tokens[1].text
        if len(name) != 3 or not name.isalpha():
            raise self._fail(tokens[1].span, "三角形的三个顶点要用三个字母，如 △ABC")
        corners = [self.scope.point(letter, self.source, tokens[1].span).node_id for letter in name]
        for first, second in zip(corners, corners[1:] + corners[:1], strict=False):
            self._add_segment(first, second, f"{first}{second}")

    def _add_segment(self, first: str, second: str, name: str) -> str:
        node_id = name
        if node_id in self.figure.nodes:
            node_id = f"{name}_seg"
        node = Node(
            id=node_id,
            kind=SEGMENT,
            role="derived",
            op="segment.free",
            args=[first, second],
        )
        self.figure.add_node(node)
        self.scope.objects[name] = Ref(
            name=name, kind="segment", node_id=node_id, endpoints=(first, second)
        )
        return node_id

    # -- NAME = 命令(参数, ...) --------------------------------------------

    def _parse_assignment(self, name_token: Token, rest: list[Token]) -> None:
        if name_token.kind is not TokenKind.IDENT:
            raise self._fail(name_token.span, "左边应该是一个名字")
        name = name_token.text
        command_token = rest[0]
        if command_token.kind not in {TokenKind.IDENT, TokenKind.KEYWORD}:
            raise self._fail(command_token.span, "这里应该是一个命令名")
        args = self._parse_call(command_token, rest)
        self._build(command_token.text, args, name, command_token.span)

    # -- 数 a = 2.5 ---------------------------------------------------------

    def _parse_text(self, tokens: list[Token]) -> None:
        """``文本 T("...", x, y)`` -- a note on the paper, not geometry."""
        if (
            len(tokens) != 9
            or tokens[1].kind is not TokenKind.IDENT
            or not tokens[2].is_punct("(")
            or tokens[3].kind is not TokenKind.STRING
            or not tokens[4].is_punct(",")
            or tokens[5].kind is not TokenKind.NUMBER
            or not tokens[6].is_punct(",")
            or tokens[7].kind is not TokenKind.NUMBER
            or not tokens[8].is_punct(")")
        ):
            raise self._fail(
                tokens[0].span,
                '这一行应该是：文本 名字("内容", x, y)',
            )
        name = tokens[1].text
        content = tokens[3].text
        x, y = tokens[5].text, tokens[7].text
        node = Node(
            id=name,
            kind=TEXT,
            role=FREE,
            args=[content],
            coords=(x, y),
            placement=(x, y),
        )
        self._install(node, tokens[1].span)
        self.scope.objects[name] = Ref(
            name=name, kind=TEXT, node_id=name, endpoints=()
        )

    def _parse_number(self, tokens: list[Token]) -> None:
        """A constant the lesson can drag: ``数 a = 2.5``.

        The value is kept exact (``5/2``); a decimal is only how it was
        typed.  A construction that uses it gets the exact constant, so
        a circle whose radius is ``a`` still has an exact radius.
        """
        if len(tokens) != 4:
            raise self._fail(tokens[0].span, "这一行应该是：数 名字 = 数值")
        name_token, equals, value = tokens[1], tokens[2], tokens[3]
        if name_token.kind is not TokenKind.IDENT:
            raise self._fail(name_token.span, "数的名字应该是一个标识符")
        if not equals.is_punct("="):
            raise self._fail(equals.span, "名字后面应该是 =")
        if value.kind is not TokenKind.NUMBER:
            raise self._fail(value.span, "= 后面应该是一个数（整数、小数或分数）")
        try:
            exact = str(sp.Rational(value.text))
        except (TypeError, ValueError, ZeroDivisionError):
            raise self._fail(value.span, f"{value.text!r} 不是一个数") from None
        node = Node(
            id=name_token.text,
            kind=NUMBER,
            role=FREE,
            op="number.free",
            args=[exact],
            label=name_token.text,
        )
        self._install(node, value.span)
        self.scope.objects[name_token.text] = Ref(
            name=name_token.text, kind="number", node_id=name_token.text
        )

    def _parse_call(self, command_token: Token, tokens: list[Token]) -> list[Arg]:
        args, _ = self._parse_call_at(command_token, tokens, 1)
        return args

    def _parse_call_at(
        self, command_token: Token, tokens: list[Token], start: int
    ) -> tuple[list[Arg], int]:
        if start >= len(tokens) or not tokens[start].is_punct("("):
            raise self._fail(command_token.span, "命令后面应该跟括号里的参数")
        index = start + 1
        args: list[Arg] = []
        if index < len(tokens) and tokens[index].is_punct(")"):
            return args, index + 1
        while True:
            token = self._peek(tokens, index)
            if token is None:
                raise self._fail(command_token.span, "括号没有关上")
            if token.kind is TokenKind.NUMBER:
                args.append(Arg(kind="number", value=token.text, name=token.text))
                index += 1
            elif token.kind is TokenKind.IDENT:
                args.append(self._resolve_name(token))
                index += 1
            else:
                raise self._fail(token.span, "这里应该是一个参数")
            following = self._peek(tokens, index)
            if following is not None and following.is_punct(","):
                index += 1
                continue
            break
        closing = self._peek(tokens, index)
        if closing is None or not closing.is_punct(")"):
            raise self._fail(command_token.span, "括号没有关上")
        return args, index + 1

    def _resolve_name(self, token: Token) -> Arg:
        name = token.text
        if name in SELECTORS:
            # The canonical value goes into the graph; the Chinese word is
            # how a person writes it.
            return Arg(kind="selector", value=SELECTORS[name], name=name)
        ref = self.scope.objects.get(name)
        if ref is not None:
            return Arg(
                kind=ref.kind,
                node_id=ref.node_id,
                name=name,
                endpoints=ref.endpoints,
            )
        if len(name) == 2 and name.isalpha():
            first = self.scope.objects.get(name[0])
            second = self.scope.objects.get(name[1])
            if first is not None and second is not None:
                if first.kind != "point" or second.kind != "point":
                    raise self._fail(token.span, f"{name!r} 只能由两个点组成")
                return Arg(
                    kind="segment",
                    node_id="",
                    name=name,
                    endpoints=(first.node_id, second.node_id),
                )
        raise self._fail(token.span, f"未定义的对象 {name!r}")

    # -- 断言 命令(参数, ...) ----------------------------------------------

    def _parse_attribute(self, tokens: list[Token], hidden: bool) -> None:
        """\u9690\u85cf l -- the object is not drawn.  \u8f85\u52a9 l -- it is dashed."""
        if len(tokens) != 2:
            raise self._fail(
                tokens[0].span,
                "\u8fd9\u4e00\u884c\u5e94\u8be5\u662f\u4e00\u4e2a\u5bf9\u8c61\u7684\u540d\u5b57",
            )
        name = tokens[1].text
        node = self.figure.nodes.get(name)
        if node is None:
            raise self._fail(tokens[1].span, f"\u6ca1\u6709\u53eb {name!r} \u7684\u5bf9\u8c61")
        if hidden:
            node.style = replace(node.style, visible=False)
        else:
            node.style = replace(node.style, line_style="dashed")

    def _parse_label_visibility(self, tokens: list[Token], visible: bool) -> None:
        """隐藏标签 l / 显示标签 l -- draw the name or not."""
        if len(tokens) != 2:
            raise self._fail(tokens[0].span, "这一行应该是：属性 对象")
        name = tokens[1].text
        node = self.figure.nodes.get(name)
        if node is None:
            raise self._fail(tokens[1].span, f"没有叫 {name!r} 的对象")
        node.style = replace(node.style, label_visible=visible)

    def _parse_appearance(self, tokens: list[Token], field: str) -> None:
        """颜色 / 线宽 / 点大小 / 标签位置 -- how one object is drawn.

        Appearance never changes geometry: a red segment is the same
        segment.  So this is the one family of statements that may come
        anywhere after the object exists, and that the kernel never has
        to re-evaluate.
        """
        if len(tokens) != 3:
            raise self._fail(tokens[0].span, "这一行应该是：属性 对象 值")
        name = tokens[1].text
        node = self.figure.nodes.get(name)
        if node is None:
            raise self._fail(tokens[1].span, f"没有叫 {name!r} 的对象")
        value = tokens[2]
        text = value.text
        if field == "color":
            if text == DEFAULT:
                node.style = replace(node.style, color="#000000")
                return
            color = resolve_color(text)
            if color is None:
                raise self._fail(
                    value.span,
                    f"没有这个颜色：{text!r}（可用：黑/红/蓝/绿/橙/紫/灰/棕）",
                )
            node.style = replace(node.style, color=color)
            return
        if field == "label_pos":
            if text in {DEFAULT, "自动"}:
                node.style = replace(node.style, label_pos=None)
                return
            if text not in LABEL_DIRECTIONS:
                raise self._fail(
                    value.span,
                    f"没有这个方位：{text!r}"
                    "（可用：右上/左上/右下/左下/上/下/左/右/自动）",
                )
            node.style = replace(node.style, label_pos=text)
            return
        table = LINE_WIDTHS if field == "width" else POINT_SIZES
        if text in table:
            number = table[text]
        elif value.kind is TokenKind.NUMBER:
            number = float(text)
        else:
            words = "/".join(table)
            raise self._fail(
                value.span, f"这里应该是数字或 {words}，实际是 {text!r}"
            )
        if number <= 0:
            raise self._fail(value.span, "大小必须是正数")
        if field == "width":
            node.style = replace(node.style, line_width=number)
        else:
            node.style = replace(node.style, point_size=number)

    def _parse_assertion(self, tokens: list[Token]) -> None:
        if len(tokens) < 2:
            raise self._fail(tokens[0].span, "断言后面应该是一个关系")
        command_token = tokens[1]
        args = self._parse_call(command_token, tokens[1:])
        command = self._resolve(command_token.text, args, command_token.span, judgement=True)
        self._add_relation(command, args)

    # -- 约束: a condition the figure has to satisfy ---------------------

    def _parse_constraint(self, tokens: list[Token]) -> None:
        """A condition the figure has to satisfy (约束).

        Two shapes, one meaning -- an expression that must be zero::

            约束 垂直(AB, AC)          a judgement
            约束 长度(AB) = 5          an equation
            约束 角度(B, A, C) = 40
            约束 长度(AB) = 长度(AC)

        The pieces are recorded here and turned into expressions *after*
        the whole script is read: a constraint may name an object that
        comes later, and a judgement needs the figure to be evaluated
        before it can produce its expression.
        """
        if len(tokens) < 2:
            raise self._fail(
                tokens[0].span, "约束后面应该是一个条件，例如 约束 垂直(AB, AC)"
            )
        command_token = tokens[1]
        if command_token.kind not in {TokenKind.IDENT, TokenKind.KEYWORD}:
            raise self._fail(command_token.span, "这里应该是一个条件名")
        args, index = self._parse_call_at(command_token, tokens, 2)
        label = f"{command_token.text}({', '.join(arg.name for arg in args)})"
        right: Expr | None = None
        right_call: tuple[Token, list[Arg]] | None = None
        if index < len(tokens) and tokens[index].is_punct("="):
            token = self._peek(tokens, index + 1)
            if token is None:
                raise self._fail(tokens[-1].span, "等号后面还缺一个数")
            if token.kind is TokenKind.NUMBER:
                right = self._number(token)
                index += 2
            elif token.kind is TokenKind.IDENT:
                call_args, after = self._parse_call_at(token, tokens, index + 2)
                right_call = (token, call_args)
                index = after
            else:
                raise self._fail(
                    token.span, "等号后面应该是一个数，或者 长度(…)、角度(…) 这样的量"
                )
            label += " = …"
        if index != len(tokens):
            raise self._fail(tokens[index].span, "约束后面多了东西")
        self.constraints.append(
            _Pending(
                label=label,
                command=command_token,
                args=args,
                right=right,
                right_call=right_call,
            )
        )

    def _relation_expression(self, command_token: Token, args: list[Arg]) -> Expr:
        """A judgement, as the expression that must vanish for it to hold."""
        candidates = lookup_all(command_token.text)
        if candidates and all(candidate.kind != JUDGEMENT for candidate in candidates):
            raise self._fail(
                command_token.span,
                f"{command_token.text!r} 不是一个条件 —— 约束要用 垂直/平行/共线/"
                "共圆/相等/中点 这样的判定，或者写成 长度(AB) = 5",
            )
        command = self._resolve(
            command_token.text, args, command_token.span, judgement=True
        )
        if command.kind != JUDGEMENT:
            raise self._fail(
                command_token.span,
                f"{command_token.text!r} 不是一个条件 —— 约束要用 垂直/平行/共线/"
                "共圆/相等/中点 这样的判定，或者写成 长度(AB) = 5",
            )
        expanded = _expand_segments(args)
        if len(expanded) != command.arity:
            expanded = args
        ids = [_relation_arg(arg) for arg in expanded]
        spec = JudgeRegistry().spec(command.id)
        context = JudgeContext(figure=self.figure, ctx=OpContext(self.figure))
        return spec.impl(context, ids)

    def _measure_expression(self, command_token: Token, args: list[Arg]) -> Expr:
        """A measurement, as the exact number it measures."""
        command = self._resolve(
            command_token.text, args, command_token.span, judgement=False
        )
        if command.kind != MEASUREMENT:
            raise self._fail(
                command_token.span,
                f"{command_token.text!r} 不是一个数 —— 等式的两边要用 "
                "长度/距离/角度/面积/半径 这样的量，或者一个数",
            )
        ids = [
            self._segment_node(arg) if arg.kind == "segment" else _operator_arg(arg)
            for arg in args
        ]
        impl = _operators().implementation(command.id)
        if impl is None:  # pragma: no cover - every measurement is implemented
            raise self._fail(command_token.span, f"命令 {command_token.text!r} 还没有实现")
        try:
            result = impl(OpContext(self.figure), ids)
        except StateError as exc:
            raise self._fail(command_token.span, f"{command_token.text!r} 量不出来：{exc}") from None
        value = result.get("value")
        if not isinstance(value, tuple) or not value:
            raise self._fail(command_token.span, f"{command_token.text!r} 不是一个数")
        return value[0]

    def _solve_constraints(self) -> None:
        """Find coordinates that satisfy every constraint, exactly."""
        if not self.constraints:
            return
        # The judgements read the evaluated figure (a line's coefficients
        # live in the cache), so the figure is evaluated first.
        evaluate_figure(self.figure, _operators())
        conditions: list[Condition] = []
        for pending in self.constraints:
            if pending.right is None and pending.right_call is None:
                expression = self._relation_expression(pending.command, pending.args)
            else:
                left = self._measure_expression(pending.command, pending.args)
                if pending.right is not None:
                    expression = left - pending.right
                else:
                    token, args = pending.right_call  # type: ignore[misc]
                    expression = left - self._measure_expression(token, args)
            conditions.append(Condition(pending.label, expression))

        outcome = solve(self.figure, conditions)
        if not outcome.ok:
            raise self._fail(
                self.constraints[0].command.span,
                f"约束解不出来：{outcome.reason}",
            )
        for node_id, (x, y) in outcome.placements.items():
            node = self.figure.nodes.get(node_id)
            if node is not None:
                node.placement = (x, y)
        self.figure.runtime["solution"] = {
            "degrees_of_freedom": outcome.degrees_of_freedom,
            "moved": list(outcome.moved),
        }

    def _add_relation(self, command: CommandSpec, args: list[Arg]) -> None:
        """Record a relation about the figure."""
        # A relation is about *points*. ``断言 相等(AB,AC)`` is the way a
        # paper writes it; the relation underneath is about A, B, A and C.
        expanded = _expand_segments(args)
        if len(expanded) != command.arity:
            expanded = args
        relation_id = f"r{len(self.figure.relations) + 1}"
        self.figure.add_relation(
            Relation(
                id=relation_id,
                kind=command.id,
                args=[_relation_arg(arg) for arg in expanded],
            )
        )

    # -- building ----------------------------------------------------------

    def _resolve(
        self,
        name: str,
        args: list[Arg],
        span: Span,
        judgement: bool | None,
    ) -> CommandSpec:
        """Find the command this call means.

        GeoGebra overloads some names, so the *arguments* decide: the
        candidates are tried in order and the first whose parameters fit
        wins. ``judgement`` says which kind is wanted -- ``True`` for an
        assertion, ``False`` for a construction, ``None`` for a bare call,
        where a construction is preferred and a relation is the fallback.
        """
        candidates = lookup_all(name)
        if not candidates:
            raise self._fail(span, self._unknown_command(name, args))
        if judgement is None:
            order = [c for c in candidates if c.kind != JUDGEMENT]
            order += [c for c in candidates if c.kind == JUDGEMENT]
        elif judgement:
            order = [c for c in candidates if c.kind == JUDGEMENT]
        else:
            order = [c for c in candidates if c.kind != JUDGEMENT]
        unimplemented = False
        for command in order:
            if command.kind == JUDGEMENT:
                if _judgement_fits(command, args):
                    if not command.implemented:
                        unimplemented = True
                        continue
                    return _resolve_alias(command)
                continue
            if not variadic_command(command) and command.arity != len(args):
                continue
            if not command.implemented:
                unimplemented = True
                continue
            if self._fits(command, args):
                return _resolve_alias(command)
        if unimplemented:
            raise self._fail(span, f"命令 {name!r} 尚未实现")
        raise self._fail(span, f"命令 {name!r} 不能接受这些参数")

    def _unknown_command(self, name: str, args: list[Arg]) -> str:
        """Why this command is not a command -- and what to write instead.

        The error is the *teaching* channel: it goes straight back to
        whoever wrote the line, and a complaint that says what to do
        gets the line fixed.  "Unknown command 'A'" says nothing; "a
        free point is written 点 A(x, y)" is a sentence somebody can
        act on.
        """
        if len(args) == 2 and all(arg.kind == "number" for arg in args):
            # `A(0,0)` -- two numbers in brackets is a point, and a point
            # is declared with 点 in front.  This is the mistake a model
            # makes most often, so it is the one worth naming.
            return (
                f"自由点要写成「点 {name}(x, y)」——"
                f"「点」字不能省（你写的是 {name}({args[0].value}, {args[1].value})）"
            )
        near = _closest_command(name)
        if near:
            return f"不认识的命令 {name!r}；你是不是想写「{near}」？"
        return f"不认识的命令 {name!r}"

    def _fits(self, command: CommandSpec, args: list[Arg]) -> bool:
        """Do these arguments fit this operator's contract?"""
        command = _resolve_alias(command)
        if command.id == "point.free":
            # A free point is handled by the store, not by an operator:
            # its arguments are two numbers.
            return len(args) == 2 and all(arg.kind == "number" for arg in args)
        spec = _operator_spec(command.id)
        if spec is None:
            return False
        variadic = bool(spec.args) and spec.args[-1].variadic
        required = len(spec.args) - 1 if variadic else len(spec.args)
        if variadic:
            if len(args) < required:
                return False
        elif len(args) != len(spec.args):
            return False
        for index, argument in enumerate(args):
            argument_spec = spec.args[min(index, len(spec.args) - 1)]
            allowed = _TYPE_FITS.get(argument_spec.type)
            if allowed is None or argument.kind not in allowed:
                return False
        return True

    def _segment_node(self, arg: Arg) -> str:
        """The node id of a segment argument, creating it if it was implied.

        ``断言``-style writing says "BC" for the segment between B and C.
        When an operator wants a line, that segment has to exist as an
        object -- so it is created, once.
        """
        if arg.node_id:
            return arg.node_id
        first, second = arg.endpoints
        name = f"{first}{second}"
        if name in self.scope.objects:
            return self.scope.objects[name].node_id
        return self._add_segment(first, second, name)

    def _build(
        self,
        command_name: str,
        args: list[Arg],
        name: str,
        span: Span,
    ) -> None:
        command = self._resolve(command_name, args, span, judgement=False)
        if command.id == "point.free":
            if len(args) != 2 or any(arg.kind != "number" for arg in args):
                raise self._fail(span, "点的坐标应该是两个数")
            self._add_free_point(name, args[0].value, args[1].value, span)
            return
        kind = _KIND_BY_COMMAND.get(command.id)
        if kind is None:
            raise self._fail(span, f"命令 {command_name!r} 还没有实现")
        operator_args = [
            self._segment_node(arg) if arg.kind == "segment" else _operator_arg(arg)
            for arg in args
        ]
        node = Node(
            id=name,
            kind=kind,
            role="attached" if command.id in Figure.ATTACHING_OPS else "derived",
            op=command.id,
            args=operator_args,
        )
        self._install(node, span)
        # A segment remembers its two ends, so that a relation may be
        # written the way a paper writes it -- ``断言 相等(AB, AC)`` --
        # rather than only as four points.  Without the ends, a segment
        # that was *drawn* could not be opened up, while the same
        # segment written as two letters could.
        endpoints: tuple[str, ...] = ()
        if command.id == "segment.free" and len(operator_args) == 2:
            endpoints = (str(operator_args[0]), str(operator_args[1]))
        self.scope.objects[name] = Ref(
            name=name, kind=kind, node_id=name, endpoints=endpoints
        )

    def _install(self, node: Node, span: Span) -> None:
        """Put an object into the figure, replacing one with the same name.

        A label may be defined again -- GeoGebra allows it, and a
        construction often wants two steps with one name: rotate a point,
        then scale it, and call the result ``D``.  The new definition
        replaces the old one, and everything that used the name follows,
        because dependents point at the **id**, not at the definition.

        What is *not* allowed is a definition that runs through itself:
        ``D = 中点(D, B)`` has no answer, and neither has ``D`` defined
        through ``E`` while ``E`` is defined through ``D``.
        """
        if node.id not in self.figure.nodes:
            self.figure.add_node(node)
            return
        if self._depends_on(node, node.id):
            raise self._fail(
                span,
                f"{node.id!r} 的定义绕回了它自己 —— "
                f"中间结果换个名字：先写 E = …，再写 {node.id} = …(E, …)",
            )
        self.figure.replace_node(node)

    def _depends_on(self, node: Node, name: str) -> bool:
        """Does this definition reach ``name`` through the figure?"""
        seen: set[str] = set()
        pending = [arg for arg in node.args if arg in self.figure.nodes]
        while pending:
            current = pending.pop()
            if current == name:
                return True
            if current in seen:
                continue
            seen.add(current)
            # An operator's arguments are not all node ids: a rotation
            # carries an angle, a selector carries an index.  Only the
            # ids lead anywhere.
            pending.extend(
                arg for arg in self.figure.nodes[current].args if arg in self.figure.nodes
            )
        return False

    # -- names -------------------------------------------------------------

    def _auto_name(self, command: CommandSpec) -> str:
        count = self._auto_names.get(command.id, 0) + 1
        self._auto_names[command.id] = count
        base = command.name_en.lower().replace(" ", "_")
        return f"{base}{count}"


#: What kind of object each operator produces.
_KIND_BY_COMMAND: dict[str, str] = {
    "point.midpoint": POINT,
    "point.centroid": POINT,
    "point.circumcenter": POINT,
    "point.incenter": POINT,
    "point.excenter": POINT,
    "point.orthocenter": POINT,
    "point.on_line": POINT,
    "point.on_circle": POINT,
    "point.foot": POINT,
    "point.intersect_lines": POINT,
    "point.intersect_line_circle": POINT,
    "point.intersect_circles": POINT,
    "point.nearest_on_object": POINT,
    "transform.reflect_point": POINT,
    "transform.mirror": POINT,
    "transform.translate": POINT,
    "transform.rotate": POINT,
    "transform.dilate": POINT,
    "line.free": LINE,
    "line.perpendicular_through": LINE,
    "line.parallel_through": LINE,
    "line.perpendicular_bisector": LINE,
    "line.angle_bisector": LINE,
    "line.tangent": LINE,
    "segment.free": SEGMENT,
    "segment.perpendicular": SEGMENT,
    "circle.free": CIRCLE,
    "circle.center_point": CIRCLE,
    "circle.through": CIRCLE,
    "circle.incircle": CIRCLE,
    "polygon.free": POLYGON,
    "polygon.regular": POLYGON,
    "polyline.free": POLYLINE,
    "ray.free": RAY,
    "arc.free": ARC,
    "arc.three_points": ARC,
    "sector.three_points": SECTOR,
    "point.polygon_vertex": POINT,
    "point.affine_ratio": POINT,
    "line.polar": LINE,
    "measure.distance": NUMBER,
    "measure.length": NUMBER,
    "measure.area": NUMBER,
    "measure.perimeter": NUMBER,
    "measure.angle": NUMBER,
    "measure.radius": NUMBER,
    "measure.slope": NUMBER,
    "measure.direction": NUMBER,
}


def _operator_arg(arg: Arg) -> str:
    """The argument as an operator wants it: a node id, a number, a selector."""
    if arg.kind == "number":
        # A number written as a literal is its text; a number named in
        # the script is the node that holds it.
        return arg.value or arg.node_id
    if arg.kind == "selector":
        return arg.value
    return arg.node_id


def _relation_arg(arg: Arg) -> str:
    """The argument as a relation wants it: a node id."""
    return arg.node_id or arg.name


def _expand_segments(args: list[Arg]) -> list[Arg]:
    """Open segments up into their two endpoints."""
    out: list[Arg] = []
    for arg in args:
        if arg.kind == "segment":
            for endpoint in arg.endpoints:
                out.append(Arg(kind="point", node_id=endpoint, name=endpoint))
        else:
            out.append(arg)
    return out


def _expands_to(args: list[Arg], arity: int) -> bool:
    """Could these arguments become ``arity`` points by opening up segments?"""
    points = 0
    for arg in args:
        if arg.kind == "segment":
            points += 2
        else:
            points += 1
    return points == arity


#: What an argument kind may be, for a relation's contract.
_JUDGEMENT_FITS: dict[str, frozenset[str]] = {
    "point": frozenset({"point"}),
    "line": frozenset({"line", "segment"}),
    "circle": frozenset({"circle"}),
    "any": frozenset({"point", "line", "segment", "circle"}),
}


def variadic_command(command: CommandSpec) -> bool:
    """Does this command take any number of trailing arguments?"""
    spec = _operator_spec(command.id)
    return bool(spec is not None and spec.args and spec.args[-1].variadic)


def _resolve_alias(command: CommandSpec) -> CommandSpec:
    """The command a synonym points at.

    ``全等`` is a synonym of ``相等``: it is the same relation, said in
    another way. The alias resolves to the judge that implements it.
    """
    if command.alias_of is None:
        return command
    target = by_id(command.alias_of)
    return target if target is not None else command


def _closest_command(name: str) -> str:
    """The command somebody probably meant, if there is one.

    A name that is one keystroke away from a command is almost always a
    typo of that command, and saying which one turns a dead end into a
    fix.

    The comparison is **exact**: an integer edit distance, with the
    number of mistakes allowed depending on how long the name is.  There
    is no similarity ratio to tune and no float to write down -- the
    kernel has no float literals (decision D18), and a fuzzy threshold
    would be one more thing whose value nobody could explain.
    """
    limit = 2 if len(name) >= 5 else 1
    best = ""
    best_distance = limit + 1
    chinese_first = _has_cjk(name)
    for command in COMMANDS:
        pairs = (
            (command.name_zh, command.name_en)
            if chinese_first
            else (command.name_en, command.name_zh)
        )
        for candidate in pairs:
            distance = _edit_distance(name, candidate, limit)
            if distance < best_distance:
                best_distance = distance
                best = candidate
    return best


def _has_cjk(text: str) -> bool:
    """Does this text contain a Chinese character?"""
    return any("\u4e00" <= character <= "\u9fff" for character in text)


def _edit_distance(first: str, second: str, limit: int) -> int:
    """How many single-character edits turn ``first`` into ``second``.

    The answer is exact, but the search stops as soon as the distance is
    known to be beyond ``limit`` -- the caller only cares whether the
    two names are close, not how close.
    """
    if abs(len(first) - len(second)) > limit:
        return limit + 1
    previous = list(range(len(second) + 1))
    for i, left in enumerate(first, start=1):
        current = [i]
        row_minimum = i
        for j, right in enumerate(second, start=1):
            if left == right:
                cost = previous[j - 1]
            else:
                cost = min(previous[j - 1], previous[j], current[j - 1]) + 1
            current.append(cost)
            row_minimum = min(row_minimum, cost)
        if row_minimum > limit:
            return limit + 1
        previous = current
    distance = previous[-1]
    return distance if distance <= limit else limit + 1


def _judgement_fits(command: CommandSpec, args: list[Arg]) -> bool:
    """Do these arguments fit this relation's contract?

    A relation may be written with segments -- ``断言 相等(AB,AC)`` -- and
    a relation is about points, so the segments are opened up before the
    check.
    """
    for variant in (args, _expand_segments(args)):
        if len(variant) != command.arity:
            continue
        if command.arg_kinds:
            allowed = [
                _JUDGEMENT_FITS.get(kind, frozenset()) for kind in command.arg_kinds
            ]
            if any(argument.kind not in kinds for argument, kinds in zip(variant, allowed, strict=False)):
                continue
        return True
    return False


#: The operator registry, built once: the parser asks it whether an
#: argument list fits an operator.
_OPERATOR_SPECS: dict[str, OpSpec] = {}
_OPERATORS: OperatorRegistry | None = None


def _operators() -> OperatorRegistry:
    """The operators, built once.

    The parser needs their *implementations* -- not just their specs --
    to turn a constraint like ``长度(AB) = 5`` into an expression.
    """
    global _OPERATORS
    if _OPERATORS is None:
        registry = OperatorRegistry()
        _register_builtins(registry)
        _OPERATORS = registry
    return _OPERATORS


def _operator_spec(command_id: str) -> OpSpec | None:
    """The contract of an operator: what its arguments must be."""
    if not _OPERATOR_SPECS:
        for spec in _operators().all_specs():
            _OPERATOR_SPECS[spec.id] = spec
    return _OPERATOR_SPECS.get(command_id)


def parse(source: str) -> Figure:
    """Parse a DSL script into a figure."""
    return Parser(source).parse()


#: The old name, kept so that existing callers keep working.
parse_dsl = parse


__all__ = ["Arg", "Parser", "Ref", "Scope", "parse", "parse_dsl"]
