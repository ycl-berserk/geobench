"""The SVG renderer: a pure function of (figure, style, view)."""

from __future__ import annotations

from geobench.evaluate import evaluate_figure
from geobench.model import Figure, Node, Style
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry
from geobench.render import COMPETITION, PLAIN, View, fit_view, get_style, render_svg


def _triangle() -> Figure:
    registry = OperatorRegistry()
    register_builtins(registry)
    figure = Figure(id="fig_render")
    for node_id, (x, y) in {"A": ("0", "0"), "B": ("6", "0"), "C": ("2", "4")}.items():
        figure.add_node(
            Node(
                id=node_id,
                kind="point",
                role="free",
                coords=(f"x_{node_id}", f"y_{node_id}"),
                placement=(x, y),
                label=node_id,
            )
        )
    figure.add_node(
        Node(id="l1", kind="line", role="derived", op="line.free", args=["A", "B"], label="AB")
    )
    figure.add_node(
        Node(id="c1", kind="circle", role="derived", op="circle.through", args=["A", "B", "C"], label="⊙O")
    )
    figure.add_node(
        Node(id="M", kind="point", role="derived", op="point.midpoint", args=["A", "B"], label="M")
    )
    evaluate_figure(figure, registry)
    return figure


def test_svg_is_well_formed() -> None:
    svg = render_svg(_triangle())
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert svg.count("<svg") == 1
    assert "<circle" in svg
    assert "<line" in svg
    assert "<text" in svg


def test_rendering_is_deterministic() -> None:
    figure = _triangle()
    assert render_svg(figure) == render_svg(figure)


def test_labels_are_rendered() -> None:
    svg = render_svg(_triangle())
    assert ">A<" in svg
    assert ">B<" in svg
    assert ">C<" in svg
    assert ">M<" in svg


def test_invisible_nodes_are_not_drawn() -> None:
    figure = _triangle()
    figure.nodes["C"].style = Style(visible=False)
    svg = render_svg(figure)
    assert ">C<" not in svg


def test_style_preset_changes_the_stroke() -> None:
    figure = _triangle()
    plain = render_svg(figure, PLAIN)
    competition = render_svg(figure, COMPETITION)
    assert plain != competition
    assert "#1f2933" in plain
    assert "#000000" in competition


def test_unknown_style_is_rejected() -> None:
    try:
        get_style("nope")
    except ValueError:
        return
    raise AssertionError("an unknown style must be rejected")


def test_view_fits_the_figure() -> None:
    figure = _triangle()
    view = fit_view(figure)
    assert view.x_min < 0 < view.x_max
    assert view.y_min < 0 < view.y_max


def test_explicit_view_is_respected() -> None:
    svg = render_svg(_triangle(), view=View(-1, -1, 7, 5))
    assert 'width="640"' in svg
