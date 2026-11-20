"""The competition figure style.

The style preset follows the conventions that competition papers actually use.
These are not invented here: TikZ's defaults are the de-facto standard for
olympiad figures (0.4pt stroke, 1.5pt point radius, Times-family serif
labels), and Chinese olympiad papers add a few house rules of their own --
auxiliary lines dashed and unlabelled, circle written as ``⊙O``, the caption
("如图") living in the statement rather than inside the image.

The style lives in its own module because **two** backends read it: the SVG
writer (geobench.render) and the screen painter (geobench.app). It carries
rendering attributes only and never affects geometry (decision D20).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FigureStyle:
    """Rendering attributes. Never affects geometry."""

    name: str = "competition"
    stroke: str = "#000000"
    stroke_width: float = 0.4
    auxiliary_stroke_width: float = 0.25
    # A point has to be visible to be clicked on, and a one-and-a-half
    # pixel dot is not: it is smaller than the letter beside it.
    point_radius: float = 3.0
    derived_point_radius: float = 2.6
    derived_point_filled: bool = True
    font_family: str = "Times New Roman, STIX Two Text, serif"
    font_size: float = 10.0
    # How far a label sits from its point, in **pixels**. In figure
    # units it would grow with the zoom, and a label would fly away
    # from the point it belongs to.
    label_offset: float = 11.0
    background: str = "none"
    sector_fill: str = "#e9e9e9"
    padding: float = 0.6
    auxiliary_ids: tuple[str, ...] = ()
    """The node ids that are auxiliary objects.

    An auxiliary object supports the figure but is not part of the
    problem's statement -- the altitude, the perpendicular bisector, the
    auxiliary circle. Chinese competition papers draw them dashed and
    thinner, and do not label them.

    There is no automatic rule for this: whether a line is auxiliary
    depends on what the problem says, not on what the line is. So it is
    stated, per figure, and the two backends read the same list.
    """

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "stroke": self.stroke,
            "stroke_width": self.stroke_width,
            "auxiliary_stroke_width": self.auxiliary_stroke_width,
            "point_radius": self.point_radius,
            "derived_point_radius": self.derived_point_radius,
            "derived_point_filled": self.derived_point_filled,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "label_offset": self.label_offset,
            "background": self.background,
            "padding": self.padding,
            "auxiliary_ids": list(self.auxiliary_ids),
        }


COMPETITION = FigureStyle()
PLAIN = FigureStyle(name="plain", stroke="#1f2933", stroke_width=0.6, point_radius=2.0)


def get_style(name: str) -> FigureStyle:
    if name == "competition":
        return COMPETITION
    if name == "plain":
        return PLAIN
    raise ValueError(f"unknown style preset {name!r}")


# -- per-object appearance --------------------------------------------------
#
# A figure is drawn in one style, but one object is not the figure: the
# key point is red, the auxiliary circle is thin, the label of B sits to
# the right.  These are the values an object may override, and they are
# **named** rather than written as codes, because the DSL cannot spell a
# hex colour: `#` starts a comment.

#: The colours a teacher can pick, by name (Chinese and English).
COLORS: dict[str, str] = {
    "黑": "#000000",
    "红": "#c0392b",
    "蓝": "#1f4e9e",
    "绿": "#1e7b4a",
    "橙": "#d35400",
    "紫": "#7d3c98",
    "灰": "#6b7280",
    "棕": "#8b5a2b",
    "black": "#000000",
    "red": "#c0392b",
    "blue": "#1f4e9e",
    "green": "#1e7b4a",
    "orange": "#d35400",
    "purple": "#7d3c98",
    "grey": "#6b7280",
    "gray": "#6b7280",
    "brown": "#8b5a2b",
}

#: "no override": draw it the way the figure's style says.
DEFAULT = "默认"

#: The pickable colours, in menu order (Chinese name, hex).
COLOR_CHOICES: tuple[tuple[str, str], ...] = (
    ("黑", "#000000"),
    ("红", "#c0392b"),
    ("蓝", "#1f4e9e"),
    ("绿", "#1e7b4a"),
    ("橙", "#d35400"),
    ("紫", "#7d3c98"),
    ("灰", "#6b7280"),
    ("棕", "#8b5a2b"),
)

#: Stroke widths in points, the same unit as :class:`FigureStyle`.
LINE_WIDTHS: dict[str, float] = {"细": 0.25, "中": 0.4, "粗": 0.7}

#: Point radii in pixels.  The competition style draws a 3 px dot.
POINT_SIZES: dict[str, float] = {"小": 2.0, "中": 3.0, "大": 4.5}

#: The direction a point's label sits in, as a unit vector in **figure**
#: coordinates (y points up).  The backend multiplies it by its own
#: label offset, so the label keeps its distance when the zoom changes.
_SQRT_HALF = 0.7071067811865476
LABEL_DIRECTIONS: dict[str, tuple[float, float]] = {
    "右上": (_SQRT_HALF, _SQRT_HALF),
    "左上": (-_SQRT_HALF, _SQRT_HALF),
    "右下": (_SQRT_HALF, -_SQRT_HALF),
    "左下": (-_SQRT_HALF, -_SQRT_HALF),
    "上": (0.0, 1.0),
    "下": (0.0, -1.0),
    "左": (-1.0, 0.0),
    "右": (1.0, 0.0),
}


def resolve_color(value: str) -> str | None:
    """A colour name as a hex string, or None if the name is not one."""
    return COLORS.get(value.strip())


def describe_color(hex_value: str) -> str:
    """The name a colour is written as, for the DSL and the menu."""
    for name, code in COLORS.items():
        if code == hex_value:
            return name
    return hex_value

