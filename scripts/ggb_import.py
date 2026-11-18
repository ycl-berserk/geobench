"""Read a GeoGebra file and write the DSL for the same construction.

    python scripts/ggb_import.py 图.ggb            # print the DSL
    python scripts/ggb_import.py 图.ggb -o 图.dsl   # write it

The import is a translation: each GeoGebra command becomes the DSL line
for the same construction, and the figure is then built by our own
parser and our own kernel.  What cannot be translated is reported --
never quietly dropped, because a figure that is missing one construction
is a different figure.

``--check`` also parses and evaluates the result, which is how you find
out that the kernel accepts it.  It is not on by default: a figure with
many intersections can take a long time to evaluate exactly, and the
import itself is instant.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from geobench.errors import GeobenchError  # noqa: E402
from geobench.ggb import import_ggb  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="the .ggb to read")
    parser.add_argument("-o", "--out", type=Path, default=None, help="write the DSL here")
    parser.add_argument(
        "--check", action="store_true", help="also parse and evaluate the result"
    )
    args = parser.parse_args()

    try:
        result = import_ggb(args.file)
    except GeobenchError as exc:
        print(f"读不了 {args.file.name}：{exc}", file=sys.stderr)
        return 1

    if args.out is not None:
        args.out.write_text(result.dsl, encoding="utf-8")
        print(f"写了 {args.out}（{len(result.dsl.splitlines())} 行）")
    else:
        print(result.dsl)

    if result.warnings:
        print("改动的：", file=sys.stderr)
        for item in result.warnings:
            print(f"  · {item}", file=sys.stderr)
    if result.skipped:
        print("没导入的：", file=sys.stderr)
        for item in result.skipped:
            print(f"  · {item}", file=sys.stderr)

    if args.check:
        from geobench.dsl import parse_dsl
        from geobench.evaluate import evaluate_figure
        from geobench.operators import register_builtins
        from geobench.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtins(registry)
        try:
            figure = parse_dsl(result.dsl)
            evaluate_figure(figure, registry)
        except GeobenchError as exc:
            print(f"内核不接受这张图：{exc}", file=sys.stderr)
            return 1
        print(f"内核接受了这张图：{len(figure.nodes)} 个对象", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
