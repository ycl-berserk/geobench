"""Writing a `.ggb`: our figure in GeoGebra's language.

The import is a translation and so is the export.  What can be said in
both languages is translated; what cannot is **reported**, never
approximated silently.  A teacher who exports a figure and opens it in
GeoGebra should get the figure they saw, or a list of the objects that
did not come across -- not a different figure that looks plausible.

The file is a ZIP with ``geogebra.xml`` inside it, exactly like the
files the import reads, so an exported file goes back through the same
test: export, import, compare.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from geobench.errors import GeobenchError
from geobench.evaluate import dependency_order, evaluate_numeric
from geobench.model import Figure

__all__ = ["export_ggb"]

#: Our kind -> the XML element type GeoGebra writes.
_ELEMENT_TYPE = {
    "point": "point",
    "segment": "segment",
    "line": "line",
    "ray": "ray",
    "circle": "conic",
    "arc": "conic",
    "sector": "conic",
    "polygon": "polygon",
    "polyline": "polyline",
}

_SIMPLE = {
    "point.midpoint": "Midpoint",
    "point.centroid": "Centroid",
    "point.incenter": "Incenter",
    "point.orthocenter": "Orthocenter",
    "line.free": "Line",
    "line.perpendicular_through": "PerpendicularLine",
    "line.parallel_through": "Line",
    "line.perpendicular_bisector": "PerpendicularBisector",
    "line.angle_bisector": "AngularBisector",
    "segment.free": "Segment",
    "segment.perpendicular": "PerpendicularSegment",
    "circle.free": "Circle",
    "circle.center_point": "Circle",
    "circle.through": "Circumcircle",
    "circle.incircle": "Incircle",
    "polygon.free": "Polygon",
    "polygon.regular": "RegularPolygon",
    "polyline.free": "Polyline",
    "ray.free": "Ray",
    "arc.free": "CircularArc",
    "arc.three_points": "CircumcircularArc",
    "sector.circular": "CircularSector",
    "sector.three_points": "CircularSector",
    "transform.mirror": "Mirror",
    "transform.reflect_point": "Mirror",
    "transform.translate": "Translate",
    "transform.rotate": "Rotate",
    "transform.dilate": "Dilate",
    "point.intersect_lines": "Intersect",
}


def _number(value: object) -> str:
    """A coordinate as GeoGebra writes it."""
    try:
        return format(float(str(value)), ".15g")
    except (TypeError, ValueError):
        return str(value)


def _label(node_id: str, used: set[str]) -> str:
    """A label GeoGebra will accept; our Greek and Chinese names become o1."""
    base = node_id if node_id.isascii() and node_id.isalnum() else ""
    if not base:
        base = "o"
    name = base
    index = 1
    while name in used:
        index += 1
        name = f"{base}{index}"
    used.add(name)
    return name


class _Writer:
    def __init__(self, figure: Figure) -> None:
        self.figure = figure
        self.construction = ET.Element("construction")
        self.labels: dict[str, str] = {}
        self.used: set[str] = set()
        self.exported: set[str] = set()
        self.skipped: list[str] = []

    def label(self, node_id: str) -> str:
        if node_id not in self.labels:
            self.labels[node_id] = _label(node_id, self.used)
        return self.labels[node_id]

    def element(
        self, node_id: str, kind: str, detail: ET.Element | None = None
    ) -> None:
        element = ET.SubElement(
            self.construction,
            "element",
            {"type": _ELEMENT_TYPE.get(kind, kind), "label": self.label(node_id)},
        )
        if detail is not None:
            element.append(detail)
        node = self.figure.nodes.get(node_id)
        if node is not None:
            if not node.style.visible:
                ET.SubElement(
                    element,
                    "show",
                    {
                        "object": "false",
                        "label": "true" if node.style.label_visible else "false",
                    },
                )
            elif not node.style.label_visible:
                ET.SubElement(element, "show", {"object": "true", "label": "false"})

    def raw_element(self, label: str, kind: str) -> None:
        """An element for a helper object (an auxiliary circle or line)."""
        element = ET.SubElement(
            self.construction,
            "element",
            {"type": _ELEMENT_TYPE.get(kind, kind), "label": label},
        )
        ET.SubElement(element, "show", {"object": "false", "label": "false"})

    def command(self, name: str, inputs: list[str], outputs: list[str]) -> None:
        command = ET.SubElement(self.construction, "command", {"name": name})
        for index, value in enumerate(inputs):
            ET.SubElement(command, "input", {f"a{index}": value})
        for index, value in enumerate(outputs):
            ET.SubElement(command, "output", {f"a{index}": value})

    def coords(self, values: tuple[object, ...]) -> ET.Element:
        if len(values) == 2:
            return ET.Element(
                "coords",
                {"x": _number(values[0]), "y": _number(values[1]), "z": "1"},
            )
        return ET.Element(
            "coords",
            {
                "x": _number(values[0]),
                "y": _number(values[1]),
                "z": _number(values[2]),
            },
        )

    def payload(self, node_id: str, key: str) -> tuple[object, ...] | None:
        cache = self.figure.node(node_id).cache.get("numeric") or {}
        values = cache.get(key)
        if values is None:
            return None
        if isinstance(values, (int, float)):
            return (values,)
        return tuple(values)

    def run(self) -> list[str]:
        evaluate_numeric(self.figure)
        for node_id in dependency_order(self.figure):
            node = self.figure.node(node_id)
            if node.kind == "point" and node.role == "free":
                if node.placement is None:
                    self.skip(node_id, "没有当前位置")
                    continue
                self.element(
                    node_id,
                    "point",
                    ET.Element(
                        "coords",
                        {
                            "x": node.placement[0],
                            "y": node.placement[1],
                            "z": "1",
                        },
                    ),
                )
                self.exported.add(node_id)
                continue
            if node.kind == "text" and node.role == "free":
                position = node.placement or node.coords
                if position is None:
                    self.skip(node_id, "文本没有位置")
                    continue
                ET.SubElement(
                    self.construction,
                    "expression",
                    {
                        "label": self.label(node_id),
                        "exp": node.args[0] if node.args else "",
                        "type": "text",
                    },
                )
                element = ET.SubElement(
                    self.construction,
                    "element",
                    {"type": "text", "label": self.label(node_id)},
                )
                ET.SubElement(
                    element,
                    "startPoint",
                    {
                        "x": _number(position[0]),
                        "y": _number(position[1]),
                        "z": "1",
                    },
                )
                self.exported.add(node_id)
                continue
            if node.kind == "number":
                self.skip(node_id, "自由数和测量还不能写回 GeoGebra")
                continue
            self._derived(node_id)
        return self.skipped

    def skip(self, node_id: str, why: str) -> None:
        self.skipped.append(f"{node_id}：{why}")

    def _args(self, node_id: str) -> list[str] | None:
        node = self.figure.node(node_id)
        values: list[str] = []
        for value in node.args:
            if value in self.figure.nodes:
                if value not in self.exported:
                    self.skip(node_id, f"依赖的 {value} 没有导出")
                    return None
                values.append(self.label(value))
            else:
                values.append(str(value))
        return values

    def _element_for(self, node_id: str, kind: str) -> None:
        payload = self.payload(node_id, kind)
        if kind == "point":
            coords = self.coords(payload) if payload is not None else None
        elif kind in {"line", "ray"} and payload is not None:
            coords = self.coords(payload[:3])
        elif kind == "segment" and payload is not None and len(payload) == 4:
            x1, y1, x2, y2 = (float(str(value)) for value in payload)
            coords = ET.Element(
                "coords",
                {
                    "x": _number(y1 - y2),
                    "y": _number(x2 - x1),
                    "z": _number(x1 * y2 - x2 * y1),
                },
            )
        elif kind == "circle" and payload is not None and len(payload) == 3:
            cx, cy, r2 = (float(str(value)) for value in payload)
            # GeoGebra's conic matrix: x^2 + y^2 + A4 x + A5 y + A2 = 0.
            coords = ET.Element(
                "matrix",
                {
                    "A0": "1",
                    "A1": "1",
                    "A2": _number(cx * cx + cy * cy - r2),
                    "A3": "0",
                    "A4": _number(-cx),
                    "A5": _number(-cy),
                },
            )
        else:
            coords = None
        self.element(node_id, kind, coords)

    def _derived(self, node_id: str) -> None:
        node = self.figure.node(node_id)
        op = node.op or ""

        # The intersection selector is the one place where the two
        # languages count differently: ours from 0, GeoGebra from 1.
        if op in {"point.intersect_line_circle", "point.intersect_circles"}:
            inputs = self._args(node_id)
            if inputs is None:
                return
            inputs = [*inputs[:2], str(int(float(inputs[2])) + 1)]
            self.command("Intersect", inputs, [self.label(node_id)])
        elif op == "point.circumcenter":
            inputs = self._args(node_id)
            if inputs is None:
                return
            # GeoGebra has no Circumcenter command of its own; the centre
            # is where two perpendicular bisectors meet, which both
            # languages already say.
            first = self.label(node_id) + "_b1"
            second = self.label(node_id) + "_b2"
            self.command("PerpendicularBisector", inputs[:2], [first])
            self.command("PerpendicularBisector", inputs[1:3], [second])
            self.raw_element(first, "line")
            self.raw_element(second, "line")
            self.command("Intersect", [first, second], [self.label(node_id)])
        elif op == "point.foot":
            inputs = self._args(node_id)
            if inputs is None:
                return
            line = self.label(node_id) + "_l"
            self.command("PerpendicularLine", [inputs[0], inputs[1]], [line])
            self.raw_element(line, "line")
            self.command("Intersect", [inputs[1], line], [self.label(node_id)])
        elif op in {"point.on_line", "point.on_circle"}:
            # The constraint cannot be said in the same words, but the
            # point can be put where it is; saying so is better than a
            # figure that quietly moves.
            payload = self.payload(node_id, "coords")
            if payload is None:
                self.skip(node_id, "没有当前位置")
                return
            self.element(node_id, "point", self.coords(payload))
            self.exported.add(node_id)
            self.skip(node_id, "依附点导出为自由点，拖动时会离开原来的对象")
            return
        else:
            name = _SIMPLE.get(op)
            if name is None:
                self.skip(node_id, f"构造 {op} 还不能写回 GeoGebra")
                return
            inputs = self._args(node_id)
            if inputs is None:
                return
            self.command(name, inputs, [self.label(node_id)])

        self._element_for(node_id, node.kind)
        self.exported.add(node_id)


def export_ggb(figure: Figure, path: Path) -> list[str]:
    """Write the figure as a `.ggb`; return what could not be written."""
    writer = _Writer(figure)
    skipped = writer.run()
    root = ET.Element(
        "geogebra",
        {
            "format": "5.0",
            "version": "5.0",
            "app": "classic",
            "platform": "w",
        },
    )
    root.append(writer.construction)
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("geogebra.xml", xml)
    except OSError as exc:
        raise GeobenchError(f"写不进这个文件：{exc}") from None
    return skipped
