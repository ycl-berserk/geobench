"""Record the model's answers as the fixtures CI gates.

The convention of this project is that **every AI output is gated by
CI**: the figures the model produced are checked by the same harness
that checks them live, so a change in the kernel that breaks them is
caught before a teacher is.

This script writes the fixtures from a live run.  It talks to the
network, so it is a manual step -- the test that uses the fixtures is
the offline one (``tests/eval``).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from evals.cases import CASES  # noqa: E402
from evals.harness import run_case  # noqa: E402

from geobench.ai_settings import resolve_provider  # noqa: E402
from geobench.operators import register_builtins  # noqa: E402
from geobench.registry import OperatorRegistry  # noqa: E402

HEADER = '''"""The figures the model produced, recorded.

These are **AI outputs**, and the project's convention is that every AI
output is gated by CI: ``tests/eval`` replays them through the same
harness the live run uses, so a kernel change that breaks them is
caught before a teacher is.

They were recorded from a live run against the service the studio
would use.  Re-record them with ``scripts/record_fixtures.py`` when the
skill changes -- and when they change, say so in the changelog.
"""

from __future__ import annotations

#: The recorded answers, by the case's name.
RECORDED: dict[str, str] = {
'''

resolution = resolve_provider()
if not resolution.ok:
    print(f"没有可用的模型服务：{resolution.reason}", file=sys.stderr)
    raise SystemExit(1)

registry = OperatorRegistry()
register_builtins(registry)

chunks = [HEADER]
for case in CASES:
    result = run_case(resolution.provider, case, registry, retries=2)
    mark = "PASS" if result.passed else "FAIL"
    print(f"[{mark}] {case.name}")
    for reason in result.reasons():
        print(f"        · {reason}")
    text = result.text.strip()
    chunks.append(f'    "{case.name}": """{text}""",\n')

chunks.append("}\n")
Path(ROOT / "evals" / "fixtures.py").write_text(
    "".join(chunks), encoding="utf-8"
)
print()
print("wrote evals/fixtures.py")
