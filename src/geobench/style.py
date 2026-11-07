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
    point_radius: float = 1.5
    derived_point_radius: float = 1.5
    derived_point_filled: bool = True
    font_family: str = "Times New Roman, STIX Two Text, serif"
    font_size: float = 10.0
    label_offset: float = 0.22
    background: str = "none"
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
