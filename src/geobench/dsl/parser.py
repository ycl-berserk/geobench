"""The DSL parser: text in, construction graph out.

A recursive-descent parser over the line-oriented DSL of
``docs/dsl-spec.md``. It is deliberately strict: an unrecognised clause is an
error with an exact position, never a guess. The whole point of the DSL is
that it can be checked.

The parser builds a figure directly. It never calls a model and never makes
a network request -- that is the difference between the DSL layer and the
text2graph layer above it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from geobench.dsl.errors import DSLParseError, Span
from geobench.dsl.lexer import Line, Token, TokenKind, tokenize
from geobench.model import Figure, Node, Relation

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
        """The two endpoints of a two-letter name such as ``BC``."""
        if len(name) == 2 and name.isalpha():
            first = self.objects.get(name[0])
            second = self.objects.get(name[1])
            if first is not None and first.kind == "point":
                if second is None or second.kind != "point":
                    raise DSLParseError(span, f"未定义的点 {name[1]!r}", source)
                return (first.node_id, second.node_id)
        ref = self.objects.get(name)
        if ref is not None and len(ref.endpoints) == 2:
            return ref.endpoints
        raise DSLParseError(span, f"无法解析对象 {name!r} 的两个端点", source)

    def circle(self, name: str, source: str, span: Span) -> str:
        ref = self.objects.get(name)
        if ref is None or ref.kind != "circle":
            raise DSLParseError(span, f"未定义的圆 {name!r}", source)
        return ref.node_id


# -- parser ----------------------------------------------------------------


class Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.lines = tokenize(source)
        self.figure = Figure(id="fig_dsl")
        self.scope = Scope()

    # -- token helpers ----------------------------------------------------

    def _peek(self, tokens: list[Token], index: int) -> Token | None:
        if index < len(tokens):
            return tokens[index]
        return None

    def _expect_ident(self, tokens: list[Token], index: int, line: Line) -> tuple[str, int]:
        token = self._peek(tokens, index)
        if token is None or token.kind is not TokenKind.IDENT:
            span = token.span if token else Span(line=line.number, col=1)
            raise DSLParseError(span, "这里应该是一个名字", self.source)
        return token.text, index + 1

    def _expect_keyword(self, tokens: list[Token], index: int, line: Line, *words: str) -> int:
        token = self._peek(tokens, index)
        if token is None or not token.is_keyword(*words):
            span = token.span if token else Span(line=line.number, col=1)
            raise DSLParseError(span, f"这里应该出现 {'/'.join(words)}", self.source)
        return index + 1

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
        if head.is_keyword("点"):
            self._parse_points(tokens, line)
            return
        if head.is_keyword("断言"):
            self._parse_assertion(tokens, line)
            return
        if head.is_keyword("线段"):
            self._parse_segment_declaration(tokens, line)
            return
        if head.is_keyword("直线"):
            self._parse_line_declaration(tokens, line)
            return
        if head.is_symbol("△"):
            self._parse_triangle(tokens, line)
            return
        if head.is_symbol("⊙"):
            self._parse_circle_declaration(tokens, line)
            return
        if head.kind is TokenKind.IDENT and len(tokens) > 1 and tokens[1].is_punct("="):
            self._parse_construction(tokens, line)
            return
        raise DSLParseError(head.span, "无法识别的语句", self.source)

    def _parse_points(self, tokens: list[Token], line: Line) -> None:
        index = 1
        while index < len(tokens):
            name, index = self._expect_ident(tokens, index, line)
            if index >= len(tokens) or not tokens[index].is_punct("("):
                raise DSLParseError(
                    tokens[index].span if index < len(tokens) else Span(line.number, 1),
                    "点后面应该跟坐标 (x, y)",
                    self.source,
                )
            index += 1
            x_token = self._peek(tokens, index)
            if x_token is None or x_token.kind is not TokenKind.NUMBER:
                raise DSLParseError(
                    x_token.span if x_token else Span(line.number, 1),
                    "缺少 x 坐标",
                    self.source,
                )
            index += 1
            if index >= len(tokens) or not tokens[index].is_punct(","):
                raise DSLParseError(
                    tokens[index].span if index < len(tokens) else Span(line.number, 1),
                    "坐标之间应该有逗号",
                    self.source,
                )
            index += 1
            y_token = self._peek(tokens, index)
            if y_token is None or y_token.kind is not TokenKind.NUMBER:
                raise DSLParseError(
                    y_token.span if y_token else Span(line.number, 1),
                    "缺少 y 坐标",
                    self.source,
                )
            index += 1
            if index >= len(tokens) or not tokens[index].is_punct(")"):
                raise DSLParseError(
                    tokens[index].span if index < len(tokens) else Span(line.number, 1),
                    "坐标缺少右括号",
                    self.source,
                )
            index += 1
            node_id = name
            if node_id in self.scope.objects:
                raise DSLParseError(x_token.span, f"名字 {name!r} 已被占用", self.source)
            self.figure.add_node(
                Node(
                    id=node_id,
                    kind="point",
                    role="free",
                    coords=(f"x_{node_id}", f"y_{node_id}"),
                    placement=(x_token.text, y_token.text),
                    label=node_id,
                )
            )
            self.scope.objects[name] = Ref(name=name, kind="point", node_id=node_id)

    def _parse_triangle(self, tokens: list[Token], line: Line) -> None:
        index = 1
        names: list[str] = []
        while index < len(tokens):
            name, index = self._expect_ident(tokens, index, line)
            names.append(name)
        if len(names) == 1 and len(names[0]) == 3 and names[0].isalpha():
            names = list(names[0])
        if len(names) != 3:
            raise DSLParseError(tokens[0].span, "三角形需要三个顶点", self.source)
        for name in names:
            self.scope.point(name, self.source, tokens[0].span)
        for first, second in ((names[0], names[1]), (names[1], names[2]), (names[2], names[0])):
            segment_id = f"{first}{second}"
            self.figure.add_node(
                Node(
                    id=segment_id,
                    kind="segment",
                    role="derived",
                    op="segment.free",
                    args=[first, second],
                )
            )
            self.scope.objects[segment_id] = Ref(
                name=segment_id,
                kind="segment",
                node_id=segment_id,
                endpoints=(first, second),
            )

    def _parse_segment_declaration(self, tokens: list[Token], line: Line) -> None:
        index = 1
        name, index = self._expect_ident(tokens, index, line)
        endpoints = self.scope.pair(name, self.source, tokens[0].span)
        self.figure.add_node(
            Node(
                id=name,
                kind="segment",
                role="derived",
                op="segment.free",
                args=list(endpoints),
            )
        )
        self.scope.objects[name] = Ref(
            name=name, kind="segment", node_id=name, endpoints=endpoints
        )

    def _parse_line_declaration(self, tokens: list[Token], line: Line) -> None:
        index = self._expect_keyword(tokens, 0, line, "直线")
        name, index = self._expect_ident(tokens, index, line)
        if index >= len(tokens) or not tokens[index].is_punct("="):
            raise DSLParseError(
                tokens[index].span if index < len(tokens) else Span(line.number, 1),
                "直线声明应该是 '直线 l1 = 过 A B'",
                self.source,
            )
        index += 1
        index = self._expect_keyword(tokens, index, line, "过")
        points: list[str] = []
        while index < len(tokens):
            point_name, index = self._expect_ident(tokens, index, line)
            points.append(point_name)
        if len(points) != 2:
            raise DSLParseError(tokens[0].span, "直线需要两个点", self.source)
        for point_name in points:
            self.scope.point(point_name, self.source, tokens[0].span)
        self.figure.add_node(
            Node(id=name, kind="line", role="derived", op="line.free", args=points)
        )
        self.scope.objects[name] = Ref(
            name=name, kind="line", node_id=name, endpoints=tuple(points)
        )

    def _parse_circle_declaration(self, tokens: list[Token], line: Line) -> None:
        index = 1
        name, index = self._expect_ident(tokens, index, line)
        if index >= len(tokens) or not tokens[index].is_punct("="):
            raise DSLParseError(
                tokens[index].span if index < len(tokens) else Span(line.number, 1),
                "圆声明应该是 '⊙O = 过 A B C' 或 '⊙O = 以 A 为圆心 半径 r'",
                self.source,
            )
        index += 1
        token = self._peek(tokens, index)
        if token is not None and token.is_keyword("过"):
            index += 1
            points: list[str] = []
            while index < len(tokens):
                point_name, index = self._expect_ident(tokens, index, line)
                points.append(point_name)
            if len(points) != 3:
                raise DSLParseError(tokens[0].span, "过三点作圆需要三个点", self.source)
            for point_name in points:
                self.scope.point(point_name, self.source, tokens[0].span)
            self.figure.add_node(
                Node(id=name, kind="circle", role="derived", op="circle.through", args=points)
            )
        elif token is not None and token.is_keyword("以"):
            index += 1
            center, index = self._expect_ident(tokens, index, line)
            index = self._expect_keyword(tokens, index, line, "为圆心")
            index = self._expect_keyword(tokens, index, line, "半径")
            radius_token = self._peek(tokens, index)
            if radius_token is None or radius_token.kind is not TokenKind.NUMBER:
                raise DSLParseError(
                    radius_token.span if radius_token else Span(line.number, 1),
                    "缺少半径",
                    self.source,
                )
            index += 1
            self.scope.point(center, self.source, tokens[0].span)
            self.figure.add_node(
                Node(
                    id=name,
                    kind="circle",
                    role="derived",
                    op="circle.free",
                    args=[center, radius_token.text],
                )
            )
        else:
            raise DSLParseError(
                token.span if token else Span(line.number, 1),
                "圆只能是 '过三点' 或 '以某点为圆心'",
                self.source,
            )
        self.scope.objects[name] = Ref(name=name, kind="circle", node_id=name)

    # -- construction -----------------------------------------------------

    def _parse_construction(self, tokens: list[Token], line: Line) -> None:
        name, index = self._expect_ident(tokens, 0, line)
        index += 1  # skip '='
        if index >= len(tokens):
            raise DSLParseError(Span(line.number, 1), "等号后面缺少构造子句", self.source)
        kind, args, selector = self._parse_clause(tokens, index, line)
        if selector is not None:
            args = [*args, str(selector)]
        node = Node(
            id=name,
            kind="point" if kind.startswith("point.") else "line",
            role="derived",
            op=kind,
            args=args,
            label=name,
        )
        self.figure.add_node(node)
        self.scope.objects[name] = Ref(name=name, kind=node.kind, node_id=name)

    def _parse_clause(
        self, tokens: list[Token], index: int, line: Line
    ) -> tuple[str, list[str], object | None]:
        """Parse a construction clause into (operator, args, selector)."""
        token = tokens[index]

        # "△ABC 的内心" -- a centre of the triangle.
        if token.is_symbol("△"):
            index += 1
            name, index = self._expect_ident(tokens, index, line)
            index = self._expect_keyword(tokens, index, line, "的")
            kind_token = self._peek(tokens, index)
            centres = {
                "内心": "point.incenter",
                "外心": "point.circumcenter",
                "垂心": "point.orthocenter",
                "重心": "point.centroid",
            }
            if kind_token is None or kind_token.text not in centres:
                raise DSLParseError(
                    kind_token.span if kind_token else Span(line.number, 1),
                    "未知的三角形特殊点",
                    self.source,
                )
            index += 1
            first, second, third = self._triangle_vertices(name, token.span)
            return (centres[kind_token.text], [first, second, third], None)

        if token.kind is TokenKind.IDENT:
            following = self._peek(tokens, index + 1)

            # "X 上 P 的垂足" -- a foot on a line.
            if following is not None and following.is_keyword("上"):
                index += 2
                point_name, index = self._expect_ident(tokens, index, line)
                index = self._expect_keyword(tokens, index, line, "的")
                index = self._expect_keyword(tokens, index, line, "垂足")
                point_ref = self.scope.point(point_name, self.source, token.span)
                line_id = self._line_node(token.text, token.span)
                return ("point.foot", [point_ref.node_id, line_id], None)

            # "XY 中点" -- the midpoint of a segment.
            if following is not None and following.is_keyword("中点"):
                index += 2
                first, second = self.scope.pair(token.text, self.source, token.span)
                return ("point.midpoint", [first, second], None)

            # "L1 与 L2 的交点" / "L1 与 ⊙O 的交点"
            if following is not None and following.is_keyword("与"):
                return self._parse_intersection(tokens, index, line)

            # "△ABC 的内心" written without the triangle sign.
            if following is not None and following.is_keyword("的"):
                index += 2
                kind_token = self._peek(tokens, index)
                centres = {
                    "内心": "point.incenter",
                    "外心": "point.circumcenter",
                    "垂心": "point.orthocenter",
                    "重心": "point.centroid",
                }
                if kind_token is None or kind_token.text not in centres:
                    raise DSLParseError(
                        kind_token.span if kind_token else Span(line.number, 1),
                        "未知的三角形特殊点",
                        self.source,
                    )
                index += 1
                first, second, third = self._triangle_vertices(token.text, token.span)
                return (centres[kind_token.text], [first, second, third], None)

        # "过 P 的 L 的垂线" / "过 P 的 L 的平行线"
        if token.is_keyword("过"):
            index += 1
            point_name, index = self._expect_ident(tokens, index, line)
            index = self._expect_keyword(tokens, index, line, "的")
            line_name, index = self._expect_ident(tokens, index, line)
            index = self._expect_keyword(tokens, index, line, "的")
            kind_token = self._peek(tokens, index)
            kinds = {"垂线": "line.perpendicular_through", "平行线": "line.parallel_through"}
            if kind_token is None or kind_token.text not in kinds:
                raise DSLParseError(
                    kind_token.span if kind_token else Span(line.number, 1),
                    "只支持 '垂线' 与 '平行线'",
                    self.source,
                )
            index += 1
            point_ref = self.scope.point(point_name, self.source, token.span)
            line_id = self._line_node(line_name, token.span)
            return (kinds[kind_token.text], [point_ref.node_id, line_id], None)

        raise DSLParseError(token.span, "无法识别的构造子句", self.source)

    def _parse_intersection(
        self, tokens: list[Token], index: int, line: Line
    ) -> tuple[str, list[str], object | None]:
        first_name, index = self._expect_ident(tokens, index, line)
        index = self._expect_keyword(tokens, index, line, "与")
        second_token = self._peek(tokens, index)
        if second_token is None:
            raise DSLParseError(Span(line.number, 1), "交点缺少第二个对象", self.source)
        if second_token.is_symbol("⊙"):
            index += 1
        second_name, index = self._expect_ident(tokens, index, line)
        index = self._expect_keyword(tokens, index, line, "的")
        selector_token = self._peek(tokens, index)
        if selector_token is None or not selector_token.is_keyword("交点", "另一交点"):
            raise DSLParseError(
                selector_token.span if selector_token else Span(line.number, 1),
                "交点子句应以 '交点' 或 '另一交点' 结尾",
                self.source,
            )
        index += 1
        line_id = self._line_node(first_name, selector_token.span)
        ref = self.scope.objects.get(second_name)
        if ref is not None and ref.kind == "circle":
            circle_id = self.scope.circle(second_name, self.source, selector_token.span)
            selector: object = "other" if selector_token.text == "另一交点" else 0
            return ("point.intersect_line_circle", [line_id, circle_id], selector)
        other_id = self._line_node(second_name, selector_token.span)
        return ("point.intersect_lines", [line_id, other_id], None)

    # -- assertions -------------------------------------------------------

    def _parse_assertion(self, tokens: list[Token], line: Line) -> None:
        index = 1
        names: list[str] = []
        spans: list[Span] = []
        relation: Token | None = None
        while index < len(tokens):
            token = tokens[index]
            if token.is_keyword("共线", "共圆") or token.is_symbol("⊥", "∥") or token.is_punct("="):
                relation = token
                break
            name, index = self._expect_ident(tokens, index, line)
            names.append(name)
            spans.append(token.span)
        if relation is None:
            raise DSLParseError(Span(line.number, 1), "断言缺少关系词", self.source)
        token = relation

        relation_id = f"r{len(self.figure.relations) + 1}"
        if token.is_keyword("共线"):
            if len(names) != 3:
                raise DSLParseError(token.span, "共线断言需要三个点", self.source)
            args = [
                self.scope.point(name, self.source, span).node_id
                for name, span in zip(names, spans, strict=True)
            ]
            self.figure.add_relation(
                Relation(id=relation_id, kind="collinear", args=args, expected=True)
            )
            return
        if token.is_keyword("共圆"):
            if len(names) != 4:
                raise DSLParseError(token.span, "共圆断言需要四个点", self.source)
            args = [
                self.scope.point(name, self.source, span).node_id
                for name, span in zip(names, spans, strict=True)
            ]
            self.figure.add_relation(
                Relation(id=relation_id, kind="concyclic", args=args, expected=True)
            )
            return
        if token.is_symbol("⊥", "∥"):
            index += 1
            right_name, index = self._expect_ident(tokens, index, line)
            right_span = tokens[index - 1].span
            if token.text == "∥":
                raise DSLParseError(token.span, "平行判定器尚未实现", self.source)
            left_id = self._line_node(names[0], spans[0])
            right_id = self._line_node(right_name, right_span)
            self.figure.add_relation(
                Relation(id=relation_id, kind="perpendicular", args=[left_id, right_id], expected=True)
            )
            return
        if token.is_punct("="):
            index += 1
            right_name, index = self._expect_ident(tokens, index, line)
            right_span = tokens[index - 1].span
            left_first, left_second = self.scope.pair(names[0], self.source, spans[0])
            right_first, right_second = self.scope.pair(right_name, self.source, right_span)
            self.figure.add_relation(
                Relation(
                    id=relation_id,
                    kind="equal_length",
                    args=[left_first, left_second, right_first, right_second],
                    expected=True,
                )
            )
            return
        raise DSLParseError(token.span, "无法识别的断言关系", self.source)

    # -- helpers ----------------------------------------------------------

    def _line_node(self, name: str, span: Span) -> str:
        """The node id of the line supporting ``name``.

        A two-letter name such as ``BC`` denotes the line through B and C; if
        a segment or line with that name already exists, it is reused.
        """
        ref = self.scope.objects.get(name)
        if ref is not None and ref.kind in {"line", "segment"}:
            return ref.node_id
        if len(name) == 2 and name.isalpha():
            first = self.scope.point(name[0], self.source, span)
            second = self.scope.point(name[1], self.source, span)
            self.figure.add_node(
                Node(
                    id=name,
                    kind="line",
                    role="derived",
                    op="line.free",
                    args=[first.node_id, second.node_id],
                )
            )
            self.scope.objects[name] = Ref(
                name=name, kind="line", node_id=name, endpoints=(first.node_id, second.node_id)
            )
            return name
        raise DSLParseError(span, f"未定义的线 {name!r}", self.source)

    def _triangle_vertices(self, name: str, span: Span) -> tuple[str, str, str]:
        if len(name) != 3 or not name.isalpha():
            raise DSLParseError(span, f"三角形名 {name!r} 应当形如 ABC", self.source)
        vertices = [self.scope.point(char, self.source, span).node_id for char in name]
        return vertices[0], vertices[1], vertices[2]


def parse_dsl(source: str) -> Figure:
    """Parse a DSL script into a construction graph."""
    return Parser(source).parse()
