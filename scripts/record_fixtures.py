"""Record the model's answers as the fixtures CI gates.

The convention of this project is that **every AI output is gated by
CI**: the figures the model produced are checked by the same harness
that checks them live, so a change in the kernel that breaks them is
caught before a teacher is.

Four tables are recorded:

- the **case answers** and the **statement answers** -- the text the
  model wrote, so the gate can replay them offline;
- the **case outcomes** and the **statement outcomes** -- what each
  answer achieved, so the gate can tell "this still fails the same
  way" from "this has started working".

The two sets are kept apart because a case and a statement may well
have the same name: they are different questions about the same
figure.

The outcomes matter for the problem statements: most of them **fail**
today, and that is the point of recording them.  The gate then says
"the figure is still not what the problem asks for" -- and when one of
them starts working, the gate says so and asks for a re-recording, so
the baseline moves deliberately.

This script talks to the network, so it is a manual step -- the test
that uses the fixtures is the offline one (``tests/eval``).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from evals.cases import CASES  # noqa: E402
from evals.harness import run_all_statements, run_case  # noqa: E402
from evals.statements import STATEMENTS  # noqa: E402

from geobench.ai_settings import resolve_provider  # noqa: E402
from geobench.operators import register_builtins  # noqa: E402
from geobench.registry import OperatorRegistry  # noqa: E402

DOC = '''"""The figures the model produced, recorded.

These are **AI outputs**, and the project's convention is that every AI
output is gated by CI: ``tests/eval`` replays them through the same
harness the live run uses, so a kernel change that breaks them is
caught before a teacher is.

Four tables:

- ``RECORDED_CASES`` and ``RECORDED_STATEMENTS`` -- the answers
  themselves, by name;
- ``OUTCOMES_CASES`` and ``OUTCOMES_STATEMENTS`` -- what each answer
  achieved, so the gate can tell a failure that has not moved from one
  that has.

They were recorded from a live run against the service the studio
would use.  Re-record them with ``scripts/record_fixtures.py`` when the
skill changes -- and when they change, say so in the changelog.
"""

from __future__ import annotations

'''

CASES_HEADER = '''#: The recorded answers to the contract cases, by the case's name.
RECORDED_CASES: dict[str, str] = {
'''

STATEMENTS_HEADER = '''}

#: The recorded answers to the problem statements, by the statement's name.
RECORDED_STATEMENTS: dict[str, str] = {
'''

CASE_OUTCOMES_HEADER = '''}

#: What each recorded case answer achieved: "satisfied" or "unsatisfied".
OUTCOMES_CASES: dict[str, str] = {
'''

STATEMENT_OUTCOMES_HEADER = '''}

#: What each recorded statement answer achieved: "satisfied",
#: "unsatisfied", "refused" or "parse-failure".
OUTCOMES_STATEMENTS: dict[str, str] = {
'''


def _escape(text: str) -> str:
    """A recorded answer, safe to write into the file."""
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


resolution = resolve_provider()
if not resolution.ok:
    print(f"没有可用的模型服务：{resolution.reason}", file=sys.stderr)
    raise SystemExit(1)

registry = OperatorRegistry()
register_builtins(registry)

case_answers: list[tuple[str, str]] = []
case_outcomes: list[tuple[str, str]] = []
statement_answers: list[tuple[str, str]] = []
statement_outcomes: list[tuple[str, str]] = []

print("契约用例：")
for case in CASES:
    result = run_case(resolution.provider, case, registry, retries=2)
    mark = "PASS" if result.passed else "FAIL"
    print(f"[{mark}] {case.name}")
    for reason in result.reasons():
        print(f"        · {reason}")
    case_answers.append((case.name, result.text.strip()))
    case_outcomes.append((case.name, "satisfied" if result.passed else "unsatisfied"))

print()
print("真实题面：")
report = run_all_statements(resolution.provider, registry, retries=2)
for result in report.results:
    mark = "PASS" if result.satisfied else "FAIL"
    print(f"[{mark}] {result.statement.name}")
    for reason in result.reasons():
        print(f"        · {reason}")
    statement_answers.append((result.statement.name, result.text.strip()))
    statement_outcomes.append((result.statement.name, result.outcome))

chunks = [DOC, CASES_HEADER]
for name, text in case_answers:
    chunks.append(f'    "{name}": """{_escape(text)}""",\n')
chunks.append(STATEMENTS_HEADER)
for name, text in statement_answers:
    chunks.append(f'    "{name}": """{_escape(text)}""",\n')
chunks.append(CASE_OUTCOMES_HEADER)
for name, outcome in case_outcomes:
    chunks.append(f'    "{name}": "{outcome}",\n')
chunks.append(STATEMENT_OUTCOMES_HEADER)
for name, outcome in statement_outcomes:
    chunks.append(f'    "{name}": "{outcome}",\n')
chunks.append("}\n")

Path(ROOT / "evals" / "fixtures.py").write_text("".join(chunks), encoding="utf-8")
print()
print("wrote evals/fixtures.py")
print(f"契约用例：{sum(1 for _, o in case_outcomes if o == 'satisfied')}/{len(CASES)}")
print(
    f"真实题面：{sum(1 for _, o in statement_outcomes if o == 'satisfied')}"
    f"/{len(STATEMENTS)}"
)
