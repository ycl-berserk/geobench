"""A figure as a small, interactive web page.

The page is the figure, and the figure can be dragged -- that is the
whole of dynamic geometry, and it is what makes a diagram teach: a
teacher says "look, it stays on the circle however I move it", and the
student believes it because they can move it too.

**How it stays small.** The obvious way to make a page draggable is to
embed a geometry engine, and then the page is two megabytes.  This does
not do that: the kernel already computes the figure *numerically* for
the screen, and that numeric path is nothing but arithmetic -- so the
page gets **one JavaScript function per object**, printed from the same
exact expression the kernel would evaluate.  A figure is a few kilobytes
of formulas, plus a hundred lines of drawing code, plus one SVG.

The formulas are exact expressions printed as JavaScript; the *drawing*
is the same primitive list the screen and the SVG export use, so the
page and the printed figure are the same picture (decision D20).

What the page does not do: it has no kernel.  It cannot judge, and it
does not try -- a verdict is the product's claim, and a browser is not
where that claim is made.  It draws, it moves, and it says what it is.
"""

from __future__ import annotations

import html
import math
from collections.abc import Mapping
from pathlib import Path

import sympy as sp
from sympy import Expr

from geobench.errors import GeobenchError
from geobench.model import Figure, Node
from geobench.primitives import (
    LinePrimitive,
    PointPrimitive,
    PolygonPrimitive,
    SegmentPrimitive,
    figure_primitives,
)
from geobench.render import View, clip_line, fit_view
from geobench.style import COMPETITION, FigureStyle

#: The object kinds this page can move.  An arc's angles and a
#: measurement's position are worked out by the kernel from the
#: geometry, and porting that to the page is a bigger job than it looks:
#: until it is done, a figure with one is exported as a plain SVG and
#: the page says so.
_DRAGGABLE = frozenset({"point", "segment", "line", "ray", "circle", "polygon", "polyline"})

#: The JavaScript the page runs.  ``__DATA__`` is replaced with the
#: figure's objects.  It is written out in full rather than pulled from
#: a CDN: a page that needs the network is a page that will not open in
#: five years.
_SCRIPT = r"""
const data = __DATA__;

const svg = document.getElementById("figure");
const free = data.free;                 // name -> [x, y]
const nodes = data.nodes;               // dependency order
const names = data.names;               // the labels, for the panel
const centre = data.centre;

function compute() {
  const v = {};
  for (const [name, p] of Object.entries(free)) {
    v["x_" + name] = p[0];
    v["y_" + name] = p[1];
  }
  for (const node of nodes) {
    v[node.id] = node.f(v);
  }
  return v;
}

// -- coordinates on the page ---------------------------------------------
// The view is fixed: the picture does not rescale while a point moves,
// because a figure that jumps in size is harder to read than one that
// runs to the edge.
const view = data.view;
const scale = data.scale;
const height = data.height;

function px(x) { return (x - view.x_min) * scale; }
function py(y) { return height - (y - view.y_min) * scale; }

function el(id) { return document.getElementById(id); }

function show(id, on) {
  const node = el(id);
  if (node) node.style.display = on ? "" : "none";
}

// -- the drawing ----------------------------------------------------------
// The same primitives the kernel produces, drawn the same way: a line
// is clipped to the page, a label sits away from the figure's centre.
function render() {
  const v = compute();
  for (const node of nodes) {
    const id = node.id;
    const value = v[id];
    if (!value) { show("o-" + id, false); continue; }
    show("o-" + id, true);
    if (node.kind === "point") {
      const [x, y] = value;
      if (!isFinite(x) || !isFinite(y)) { show("o-" + id, false); continue; }
      const dot = el("o-" + id);
      dot.setAttribute("cx", px(x));
      dot.setAttribute("cy", py(y));
      const label = el("t-" + id);
      if (label) {
        const dx = x - centre[0], dy = y - centre[1];
        const len = Math.hypot(dx, dy) || 1;
        label.setAttribute("x", px(x) + (dx / len) * data.label_offset);
        label.setAttribute("y", py(y) + (dy / len) * data.label_offset);
      }
    } else if (node.kind === "line") {
      const [a, b, c] = value;
      const span = clipLine(a, b, c);
      if (!span) { show("o-" + id, false); continue; }
      const line = el("o-" + id);
      line.setAttribute("x1", px(span[0]));
      line.setAttribute("y1", py(span[1]));
      line.setAttribute("x2", px(span[2]));
      line.setAttribute("y2", py(span[3]));
    } else if (node.kind === "segment" || node.kind === "ray") {
      const [x1, y1, x2, y2] = value;
      const line = el("o-" + id);
      line.setAttribute("x1", px(x1));
      line.setAttribute("y1", py(y1));
      line.setAttribute("x2", px(x2));
      line.setAttribute("y2", py(y2));
    } else if (node.kind === "circle") {
      const [cx, cy, r2] = value;
      if (!(r2 > 0)) { show("o-" + id, false); continue; }
      const circle = el("o-" + id);
      circle.setAttribute("cx", px(cx));
      circle.setAttribute("cy", py(cy));
      circle.setAttribute("r", Math.sqrt(r2) * scale);
    } else if (node.kind === "polygon" || node.kind === "polyline") {
      const shape = el("o-" + id);
      const points = [];
      for (let i = 0; i + 1 < value.length; i += 2) {
        points.push(px(value[i]) + "," + py(value[i + 1]));
      }
      shape.setAttribute("points", points.join(" "));
    }
  }
}

// Cyrus-Beck, the same clipping the SVG export does: a line is drawn
// only where it crosses the page.
function clipLine(a, b, c) {
  if (Math.abs(a) < 1e-12 && Math.abs(b) < 1e-12) return null;
  let px0, py0;
  if (Math.abs(b) > 1e-12) { px0 = 0; py0 = -c / b; }
  else { px0 = -c / a; py0 = 0; }
  const dx = b, dy = -a;
  let low = -1e12, high = 1e12;
  const edges = [[1, 0, view.x_min], [-1, 0, -view.x_max],
                 [0, 1, view.y_min], [0, -1, -view.y_max]];
  for (const [nx, ny, offset] of edges) {
    const denom = nx * dx + ny * dy;
    const numer = offset - (nx * px0 + ny * py0);
    if (Math.abs(denom) < 1e-12) { if (numer > 0) return null; continue; }
    const t = numer / denom;
    if (denom > 0) low = Math.max(low, t); else high = Math.min(high, t);
  }
  if (low > high) return null;
  return [px0 + low * dx, py0 + low * dy, px0 + high * dx, py0 + high * dy];
}

// -- dragging --------------------------------------------------------------
let dragging = null;

function toFigure(event) {
  const box = svg.getBoundingClientRect();
  const sx = (event.clientX - box.left) * (data.width / box.width);
  const sy = (event.clientY - box.top) * (data.height / box.height);
  return [sx / scale + view.x_min, (height - sy) / scale + view.y_min];
}

svg.addEventListener("pointerdown", (event) => {
  for (const name of Object.keys(free)) {
    const dot = el("o-" + name);
    if (!dot) continue;
    const target = dot.getBoundingClientRect();
    const dx = event.clientX - (target.left + target.width / 2);
    const dy = event.clientY - (target.top + target.height / 2);
    if (Math.hypot(dx, dy) < 18) {
      dragging = name;
      svg.setPointerCapture(event.pointerId);
      event.preventDefault();
      return;
    }
  }
});

svg.addEventListener("pointermove", (event) => {
  if (!dragging) return;
  free[dragging] = toFigure(event);
  render();
});

svg.addEventListener("pointerup", () => { dragging = null; });
svg.addEventListener("pointercancel", () => { dragging = null; });

// -- the panel -------------------------------------------------------------
document.getElementById("labels").addEventListener("change", (event) => {
  for (const node of nodes) {
    if (node.kind === "point") show("t-" + node.id, event.target.checked);
  }
});

document.getElementById("reset").addEventListener("click", () => {
  for (const [name, p] of Object.entries(data.start)) free[name] = p.slice();
  render();
});

render();
"""


def _js_number(value: Expr) -> str:
    """An exact number as a JavaScript number literal."""
    number = sp.Rational(value)
    numerator, denominator = int(number.p), int(number.q)
    if denominator == 1:
        return str(numerator)
    return f"({numerator}/{denominator})"


def js_expression(expr: Expr, local: frozenset[str] = frozenset()) -> str:
    """An exact expression as a JavaScript expression.

    Only what the kernel actually builds: arithmetic, square roots,
    absolute values and the inverse trigonometric functions of an angle
    measurement.  Anything else is a bug in the caller, not something to
    guess at.

    ``local`` names are the shared subterms the caller has already
    printed as ``const`` -- they are referred to directly, while the
    figure's coordinates live in the ``v`` map.
    """
    if expr is sp.pi:
        return "Math.PI"
    if isinstance(expr, sp.Symbol):
        name = str(expr.name)
        if name in local:
            return name
        return f'v["{expr.name}"]'
    if expr.is_Number:
        return _js_number(expr)
    if isinstance(expr, sp.Add):
        return "(" + " + ".join(js_expression(arg, local) for arg in expr.args) + ")"
    if isinstance(expr, sp.Mul):
        return "(" + " * ".join(js_expression(arg, local) for arg in expr.args) + ")"
    if isinstance(expr, sp.Pow):
        base, exponent = expr.args
        if exponent == sp.Rational(1, 2):
            return f"Math.sqrt({js_expression(base, local)})"
        if exponent == 2:
            inner = js_expression(base, local)
            return f"({inner} * {inner})"
        return f"Math.pow({js_expression(base, local)}, {js_expression(exponent, local)})"
    if isinstance(expr, sp.Abs):
        return f"Math.abs({js_expression(expr.args[0], local)})"
    if isinstance(expr, sp.acos):
        return f"Math.acos({js_expression(expr.args[0], local)})"
    if isinstance(expr, sp.asin):
        return f"Math.asin({js_expression(expr.args[0], local)})"
    if isinstance(expr, sp.atan):
        return f"Math.atan({js_expression(expr.args[0], local)})"
    raise GeobenchError(f"cannot draw this expression in a page: {expr}")


def _payload(node: Node) -> tuple[Expr, ...] | None:
    """The exact expressions a node's drawing is built from."""
    if node.kind == "point":
        if node.coords is None:
            return None
        return tuple(FIELD_COERCE(text) for text in node.coords)
    for key in ("line", "segment", "circle", "polygon", "polyline", "ray"):
        value = node.cache.get(key)
        if isinstance(value, tuple) and value:
            return tuple(value)
    return None


def FIELD_COERCE(text: str) -> Expr:
    """A coordinate string as an exact expression.

    Imported lazily through the field so this module does not need the
    whole kernel to be loaded to render a page.
    """
    from geobench.field import FIELD

    return FIELD.coerce(text)


def _js_node(node: Node) -> str:
    """One object, as a function from the figure's numbers to its payload.

    The expressions share subterms -- a circumcentre's denominator appears
    once per coordinate, and a circle's radius repeats the whole centre --
    so they are printed *once* and referred to.  Without that, a page for
    a figure with a few centres is tens of kilobytes of the same formula.
    """
    payload = _payload(node)
    if payload is None:
        raise GeobenchError(f"object {node.id!r} has no drawing")
    shared, simplified = sp.cse(list(payload), optimizations="basic")
    local = frozenset(symbol.name for symbol, _ in shared)
    lines = [
        f"const {symbol.name} = {js_expression(value, local)};"
        for symbol, value in shared
    ]
    body = "[" + ", ".join(js_expression(value, local) for value in simplified) + "]"
    kind = "polyline" if node.kind == "polyline" else node.kind
    return (
        f'  {{id: "{node.id}", kind: "{kind}", f: function (v) {{ '
        + " ".join(lines)
        + f" return {body}; }}}}"
    )


def _dependencies(figure: Figure, node: Node) -> list[str]:
    return [arg for arg in node.args if arg in figure.nodes]


def _order(figure: Figure) -> list[Node]:
    """The nodes in dependency order, so each one's inputs are ready."""
    from geobench.evaluate import dependency_order

    return [figure.nodes[node_id] for node_id in dependency_order(figure)]


def html_source(
    figure: Figure,
    style: FigureStyle = COMPETITION,
    title: str = "几何图形",
    width_px: int = 640,
) -> str:
    """The figure as a self-contained page that can be dragged."""
    moving = [node for node in figure.nodes.values() if node.kind not in _DRAGGABLE]
    if moving:
        names = "、".join(node.id for node in moving[:4])
        raise GeobenchError(
            f"这张图有 {names}，交互导出暂时只支持点、线、圆、多边形 —— 先导出 SVG"
        )
    free = {
        node.id: (node.placement or ("0", "0"))
        for node in figure.nodes.values()
        if node.role == "free" and node.kind == "point"
    }
    #: The placements are exact strings ("9/5", "2*sqrt(3)"); the page
    #: works in numbers, so they are read the way the screen reads them.
    positions = {name: (_float(text[0]), _float(text[1])) for name, text in free.items()}
    if not free:
        raise GeobenchError("这张图没有自由点，没有什么可以拖动")

    view = fit_view(figure, style.padding)
    scale = width_px / view.width if view.width else 1.0
    height_px = round(view.height * scale)
    centre = _centre(figure)
    ordered = _order(figure)
    primitives = figure_primitives(figure, style)
    by_id = {primitive.id: primitive for primitive in primitives}

    drawn = [node for node in ordered if node.kind in _DRAGGABLE]
    positions_js = _js_positions({name: [x, y] for name, (x, y) in positions.items()})
    nodes_js = ",\n".join(_js_node(node) for node in drawn)
    data_js = (
        "{\n"
        f'  width: {width_px}, height: {height_px}, scale: {scale:.12g},\n'
        f'  view: {{x_min: {view.x_min:.12g}, x_max: {view.x_max:.12g}, '
        f'y_min: {view.y_min:.12g}, y_max: {view.y_max:.12g}}},\n'
        f'  centre: [{centre[0]:.12g}, {centre[1]:.12g}],\n'
        f'  label_offset: {style.label_offset * scale:.12g},\n'
        f'  free: {positions_js},\n'
        f'  start: {positions_js},\n'
        "  names: {},\n"
        "  nodes: [\n" + nodes_js + "\n  ]\n"
        "}"
    )
    script = _SCRIPT.replace("__DATA__", data_js)

    return _PAGE.format(
        title=html.escape(title),
        style=_CSS,
        body=_body(by_id, view, scale, height_px, style),
        steps=_steps(ordered),
        script=script,
    )


def _float(text: str) -> float:
    from geobench.numeric import placement_float

    value = placement_float(text)
    if value is None:
        raise GeobenchError(f"the point cannot be placed at {text!r}")
    return value


def _js_positions(values: dict[str, object]) -> str:
    items = []
    for name, value in values.items():
        if isinstance(value, list) and len(value) == 2:
            items.append(f'"{name}": [{value[0]:.12g}, {value[1]:.12g}]')
        else:
            items.append(f'"{name}": "{value}"')
    return "{" + ", ".join(items) + "}"


def _centre(figure: Figure) -> tuple[float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for node in figure.nodes.values():
        if node.kind != "point" or node.placement is None:
            continue
        x = _float(node.placement[0])
        y = _float(node.placement[1])
        xs.append(x)
        ys.append(y)
    if not xs:
        return (0.0, 0.0)
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


def _body(
    by_id: Mapping[str, object],
    view: View,
    scale: float,
    height: int,
    style: FigureStyle,
) -> str:
    """The SVG, drawn here so that every object has an id to move."""
    from geobench.primitives import CirclePrimitive, LabelPrimitive

    def tx(x: float) -> float:
        return (x - view.x_min) * scale

    def ty(y: float) -> float:
        return height - (y - view.y_min) * scale

    def fmt(value: float) -> str:
        return f"{value:.4f}".rstrip("0").rstrip(".")

    parts: list[str] = [
        f'<svg id="figure" viewBox="0 0 {round(view.width * scale)} {height}" '
        f'preserveAspectRatio="xMidYMid meet">'
    ]
    points: list[str] = []
    labels: list[str] = []
    for primitive in by_id.values():
        if isinstance(primitive, PointPrimitive):
            if not (math.isfinite(primitive.x) and math.isfinite(primitive.y)):
                continue
            radius = style.point_radius if primitive.free else style.derived_point_radius
            points.append(
                f'<circle id="o-{primitive.id}" cx="{fmt(tx(primitive.x))}" '
                f'cy="{fmt(ty(primitive.y))}" r="{fmt(radius)}" '
                f'fill="{style.stroke}"/>'
            )
            labels.append(
                f'<text id="t-{primitive.id}" x="{fmt(tx(primitive.x))}" '
                f'y="{fmt(ty(primitive.y))}" dy=".35em" text-anchor="middle">'
                f"{html.escape(primitive.label)}</text>"
            )
        elif isinstance(primitive, SegmentPrimitive):
            parts.append(
                f'<line id="o-{primitive.id}" x1="{fmt(tx(primitive.x1))}" '
                f'y1="{fmt(ty(primitive.y1))}" x2="{fmt(tx(primitive.x2))}" '
                f'y2="{fmt(ty(primitive.y2))}" stroke="{style.stroke}" '
                f'stroke-width="{style.stroke_width * 1.6}"'
                f'{_dash(primitive.auxiliary)}/>'
            )
        elif isinstance(primitive, LinePrimitive):
            span = clip_line(primitive.a, primitive.b, primitive.c, view)
            if span is None:
                continue
            parts.append(
                f'<line id="o-{primitive.id}" x1="{fmt(tx(span[0]))}" '
                f'y1="{fmt(ty(span[1]))}" x2="{fmt(tx(span[2]))}" '
                f'y2="{fmt(ty(span[3]))}" stroke="{style.stroke}" '
                f'stroke-width="{style.stroke_width * 1.6}"'
                f'{_dash(primitive.auxiliary)}/>'
            )
        elif isinstance(primitive, CirclePrimitive):
            parts.append(
                f'<circle id="o-{primitive.id}" cx="{fmt(tx(primitive.cx))}" '
                f'cy="{fmt(ty(primitive.cy))}" r="{fmt(primitive.radius * scale)}" '
                f'fill="none" stroke="{style.stroke}" '
                f'stroke-width="{style.stroke_width * 1.6}"'
                f'{_dash(primitive.auxiliary)}/>'
            )
        elif isinstance(primitive, PolygonPrimitive):
            pairs = " ".join(
                f"{fmt(tx(primitive.vertices[index]))},{fmt(ty(primitive.vertices[index + 1]))}"
                for index in range(0, len(primitive.vertices) - 1, 2)
            )
            tag = "polygon" if getattr(primitive, "closed", True) else "polyline"
            parts.append(
                f'<{tag} id="o-{primitive.id}" points="{pairs}" fill="none" '
                f'stroke="{style.stroke}" stroke-width="{style.stroke_width * 1.6}"'
                f"{_dash(primitive.auxiliary)}/>"
            )
        elif isinstance(primitive, LabelPrimitive):
            labels.append(
                f'<text id="t-{primitive.id}" x="{fmt(tx(primitive.x))}" '
                f'y="{fmt(ty(primitive.y))}" dy=".35em" text-anchor="middle">'
                f"{html.escape(primitive.text)}</text>"
            )
    parts.extend(points)
    parts.extend(labels)
    parts.append("</svg>")
    return "\n".join(parts)


def _dash(auxiliary: bool) -> str:
    return ' stroke-dasharray="5 3"' if auxiliary else ""


def _steps(nodes: list[Node]) -> str:
    """The construction, as a list a student can read."""
    items: list[str] = []
    for _index, node in enumerate(nodes, start=1):
        if node.role == "free":
            continue
        label = html.escape(node.id)
        op = html.escape(node.op or "")
        items.append(f"<li><b>{label}</b> = {op}({html.escape(', '.join(node.args))})</li>")
    return "\n".join(items)


_CSS = """
:root { color-scheme: light; }
body { margin: 0; font-family: "Times New Roman", "STIX Two Text", serif;
       background: #fbfbf9; color: #1f2933; }
main { max-width: 760px; margin: 24px auto; padding: 0 16px; }
h1 { font-size: 20px; font-weight: 600; margin: 0 0 8px; }
.hint { color: #6b7280; font-size: 13px; margin: 0 0 12px; }
#figure { width: 100%; height: auto; background: #fff;
          border: 1px solid #e5e7eb; border-radius: 6px; touch-action: none;
          cursor: grab; }
#figure:active { cursor: grabbing; }
svg text { font-family: "Times New Roman", "STIX Two Text", serif; }
.bar { display: flex; gap: 16px; align-items: center; margin: 12px 0; font-size: 14px; }
.bar label { display: flex; gap: 6px; align-items: center; cursor: pointer; }
button { font: inherit; padding: 4px 10px; border: 1px solid #cbd5e1;
         background: #fff; border-radius: 4px; cursor: pointer; }
button:hover { background: #f1f5f9; }
details { margin-top: 12px; font-size: 13px; color: #374151; }
summary { cursor: pointer; }
ol { margin: 8px 0 0 20px; padding: 0; }
li { margin: 2px 0; }
"""

_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{style}</style>
</head>
<body>
<main>
<h1>{title}</h1>
<p class="hint">拖动圆点，图形会跟着变。这不是一张图片，是一个可以动的图。</p>
{body}
<div class="bar">
  <label><input type="checkbox" id="labels" checked> 显示标签</label>
  <button id="reset" type="button">回到原位</button>
</div>
<details>
  <summary>构造步骤</summary>
  <ol>
{steps}
  </ol>
</details>
</main>
<script>{script}</script>
</body>
</html>
"""


def write_html(
    figure: Figure,
    style: FigureStyle | None,
    path: Path,
    title: str = "几何图形",
) -> None:
    path.write_text(html_source(figure, style or COMPETITION, title), encoding="utf-8")


__all__ = ["html_source", "js_expression", "write_html"]
