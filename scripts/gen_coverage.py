"""Regenerate the coverage table in docs/plan.md from the command table.

    python scripts/gen_coverage.py [--check]

The table in the plan document is the checklist the project is worked
from. It is **generated**, so it cannot drift away from the code: the
command table (:mod:`geobench.commands`) is the truth, and this script
writes the document from it.

``--check`` exits non-zero when the document is out of date, which is
what CI does.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geobench.commands import FAMILIES, by_family  # noqa: E402

PLAN = ROOT / "docs" / "plan.md"
START = "<!-- coverage:start -->"
END = "<!-- coverage:end -->"


def table() -> str:
    """The coverage table, as markdown."""
    lines: list[str] = []
    for number, family in enumerate(FAMILIES, start=1):
        commands = by_family(family)
        if not commands:
            continue
        lines.append(f"### 6.{number} {family}")
        lines.append("")
        lines.append("| GeoGebra | 中文 | 我们的算子 | 状态 |")
        lines.append("|---|---|---|---|")
        for command in commands:
            mark = "`[x]`" if command.implemented else "`[ ]`"
            lines.append(
                f"| `{command.name_en}` | {command.name_zh} | `{command.id}` | {mark} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def replace(text: str, block: str) -> str:
    """Put the block between the markers, replacing whatever was there."""
    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END), re.DOTALL
    )
    replacement = f"{START}\n\n{block}\n{END}"
    if not pattern.search(text):
        raise SystemExit(f"{PLAN} has no coverage markers")
    return pattern.sub(replacement, text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when the document is out of date",
    )
    args = parser.parse_args()

    current = PLAN.read_text(encoding="utf-8")
    updated = replace(current, table())

    if args.check:
        if current != updated:
            print(f"{PLAN} is out of date; run scripts/gen_coverage.py")
            return 1
        print(f"{PLAN} is up to date")
        return 0

    if current != updated:
        PLAN.write_text(updated, encoding="utf-8")
        print(f"{PLAN} updated")
    else:
        print(f"{PLAN} already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
