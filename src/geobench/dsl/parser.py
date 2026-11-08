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

from dataclasses import dataclass, field

from geobench.commands import (
    JUDGEMENT,
    SELECTORS,
    CommandSpec,
    by_id,
    lookup_all,
)
from geobench.dsl.errors import DSLParseError, Span
from geobench.dsl.lexer import Line, Token, TokenKind, tokenize
from geobench.model import (
    ARC,
    CIRCLE,
    FREE,
    LINE,
    NUMBER,
    POINT,
    POLYGON,
    SECTOR,
    SEGMENT,
    Figure,
    Node,
    Relation,
)
from geobench.operators import register_builtins as _register_builtins
from geobench.registry import OperatorRegistry, OpSpec

# -- object table ----------------------------------------------------------


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
    "selector": frozenset({"selector"}),
}


# -- parser ----------------------------------------------------------------


class Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.lines = tokenize(source)
        self.figure = Figure(id="fig_dsl")
        self.scope = Scope()
        self._auto_names: dict[str, int] = {}

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
        return self.figure

    def _parse_line(self, line: Line) -> None:
        tokens = line.tokens
        head = tokens[0]
        if head.is_keyword("点") or head.text == "Point":
            self._parse_points(tokens, line)
            return
        if head.is_keyword("断言"):
            self._parse_assertion(tokens)
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
            x, index = self._expect_number(tokens, index, line)
            if index >= len(tokens) or not tokens[index].is_punct(","):
                raise self._fail(tokens[index - 1].span, "两个坐标之间应该有逗号")
            index += 1
            y, index = self._expect_number(tokens, index, line)
            if index >= len(tokens) or not tokens[index].is_punct(")"):
                raise self._fail(tokens[index - 1].span, "坐标后面应该有右括号")
            index += 1
            self._add_free_point(name_token.text, x, y, name_token.span)

    def _expect_number(self, tokens: list[Token], index: int, line: Line) -> tuple[str, int]:
        token = self._peek(tokens, index)
        if token is None or token.kind is not TokenKind.NUMBER:
            span = token.span if token else Span(line=line.number, col=1)
            raise self._fail(span, "这里应该是一个数")
        return token.text, index + 1

    def _add_free_point(self, name: str, x: str, y: str, span: Span) -> None:
        if name in self.scope.objects:
            raise self._fail(span, f"名字 {name!r} 已经用过了")
        node = Node(
            id=name,
            kind=POINT,
            role=FREE,
            coords=(f"x_{name}", f"y_{name}"),
            placement=(x, y),
        )
        self.figure.add_node(node)
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
        if name in self.scope.objects:
            raise self._fail(name_token.span, f"名字 {name!r} 已经用过了")
        command_token = rest[0]
        if command_token.kind not in {TokenKind.IDENT, TokenKind.KEYWORD}:
            raise self._fail(command_token.span, "这里应该是一个命令名")
        args = self._parse_call(command_token, rest)
        self._build(command_token.text, args, name, command_token.span)

    def _parse_call(self, command_token: Token, tokens: list[Token]) -> list[Arg]:
        if len(tokens) < 2 or not tokens[1].is_punct("("):
            raise self._fail(command_token.span, "命令后面应该跟括号里的参数")
        index = 2
        args: list[Arg] = []
        if index < len(tokens) and tokens[index].is_punct(")"):
            return args
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
        return args

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

    def _parse_assertion(self, tokens: list[Token]) -> None:
        if len(tokens) < 2:
            raise self._fail(tokens[0].span, "断言后面应该是一个关系")
        command_token = tokens[1]
        args = self._parse_call(command_token, tokens[1:])
        command = self._resolve(command_token.text, args, command_token.span, judgement=True)
        self._add_relation(command, args)

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
            raise self._fail(span, f"不认识的命令 {name!r}")
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

    def _fits(self, command: CommandSpec, args: list[Arg]) -> bool:
        """Do these arguments fit this operator's contract?"""
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
            role="derived",
            op=command.id,
            args=operator_args,
        )
        self.figure.add_node(node)
        self.scope.objects[name] = Ref(name=name, kind=kind, node_id=name)

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
    "point.orthocenter": POINT,
    "point.foot": POINT,
    "point.intersect_lines": POINT,
    "point.intersect_line_circle": POINT,
    "point.intersect_circles": POINT,
    "point.nearest_on_object": POINT,
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
    "circle.free": CIRCLE,
    "circle.center_point": CIRCLE,
    "circle.through": CIRCLE,
    "circle.incircle": CIRCLE,
    "polygon.free": POLYGON,
    "arc.three_points": ARC,
    "sector.three_points": SECTOR,
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
        return arg.value
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


def _operator_spec(command_id: str) -> OpSpec | None:
    """The contract of an operator: what its arguments must be."""
    if not _OPERATOR_SPECS:
        registry = OperatorRegistry()
        _register_builtins(registry)
        for spec in registry.all_specs():
            _OPERATOR_SPECS[spec.id] = spec
    return _OPERATOR_SPECS.get(command_id)


def parse(source: str) -> Figure:
    """Parse a DSL script into a figure."""
    return Parser(source).parse()


#: The old name, kept so that existing callers keep working.
parse_dsl = parse


__all__ = ["Arg", "Parser", "Ref", "Scope", "parse", "parse_dsl"]
