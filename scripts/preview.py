"""Render the demo figures to PNG so they can be looked at.

The SVG is the artefact that goes into LaTeX or Word; the PNG is for
looking at it. This is a *preview* helper, not part of the kernel: it is
the one place where pixels are allowed.

    python scripts/preview.py
    python scripts/preview.py examples/demo-figure.svg
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TARGETS = ("examples/demo-figure.svg", "examples/dsl-demo.svg")


def svg_to_png(svg_path: Path, png_path: Path, scale: int = 2) -> None:
    """Rasterise an SVG with MuPDF.

    PyMuPDF is an optional dependency (the ``preview`` extra) because the
    kernel itself never needs pixels.
    """
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - depends on the environment
        raise SystemExit(
            "PyMuPDF is not installed. Install it with:\n"
            '    pip install -e ".[preview]"'
        ) from None

    document = pymupdf.open(svg_path)
    try:
        page = document[0]
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
        pixmap.save(png_path)
    finally:
        document.close()


def main() -> None:
    targets = sys.argv[1:] or list(DEFAULT_TARGETS)
    for name in targets:
        svg = Path(name)
        if not svg.is_absolute():
            svg = REPO_ROOT / svg
        if not svg.exists():
            print(f"skip {name}: not found")
            continue
        png = svg.with_suffix(".png")
        svg_to_png(svg, png)
        print(f"{svg.relative_to(REPO_ROOT)} -> {png.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
