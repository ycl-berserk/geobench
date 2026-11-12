"""The AI's answers are gated by CI.

The project's convention is that **every AI output goes through a
gate**: the figures the model produced are replayed through the same
harness the live run uses, so a change in the kernel that breaks them
is caught here rather than in front of a teacher.

The replay is **offline**: the provider below is a fake that answers
from the recorded fixtures.  The live measurement is a manual step
(``scripts/eval_ai.py``); this is the regression net under it.

There are two gates, because there are two questions:

- the **cases** must still pass -- that is the contract, and it is
  supposed to hold;
- the **statements** must still fail *the same way* -- most of them
  fail today, and that is the point of recording them.  The gate
  says "this figure is still not what the problem asks for", and when
  one of them starts working the gate says so and asks for a
  re-recording, so the baseline only moves on purpose.
"""

from __future__ import annotations

import pytest
from evals.cases import CASES
from evals.fixtures import (
    OUTCOMES_STATEMENTS,
    RECORDED_CASES,
    RECORDED_STATEMENTS,
)
from evals.harness import run_case, run_statement
from evals.statements import STATEMENTS

from geobench.ai import Provider
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


class ReplayProvider:
    """A provider that answers from the recorded figures.

    It looks the request up in the user's message, so the harness can
    drive it exactly as it drives a real service.
    """

    name = "replay"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        # The **longest** matching request wins.  One statement's request
        # can begin with a case's whole request ("...作圆c在P点的切线t" vs
        # "...作圆c在P点的切线t，连结OP"), and answering with the shorter
        # one would replay the wrong figure.
        candidates: list[tuple[int, str]] = []
        for case in CASES:
            if case.request in user and case.name in RECORDED_CASES:
                candidates.append((len(case.request), RECORDED_CASES[case.name]))
        for statement in STATEMENTS:
            if statement.request in user and statement.name in RECORDED_STATEMENTS:
                candidates.append(
                    (len(statement.request), RECORDED_STATEMENTS[statement.name])
                )
        if not candidates:
            raise AssertionError(f"no recorded answer for this request:\n{user[:200]}")
        return max(candidates, key=lambda pair: pair[0])[1]


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


@pytest.fixture()
def provider() -> ReplayProvider:
    return ReplayProvider()


def test_every_case_has_a_recorded_answer() -> None:
    """A case without a recorded answer is a case nobody is watching."""
    missing = [case.name for case in CASES if case.name not in RECORDED_CASES]
    assert not missing, f"这些用例还没有记录下来的答案：{missing}"


def test_every_statement_has_a_recorded_answer() -> None:
    """The same for the problem statements."""
    missing = [
        statement.name
        for statement in STATEMENTS
        if statement.name not in RECORDED_STATEMENTS
    ]
    assert not missing, f"这些题面还没有记录下来的答案：{missing}"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_the_recorded_answers_still_hold(
    case, provider: Provider, registry: OperatorRegistry
) -> None:
    """The recorded figure still satisfies what the problem asks for."""
    result = run_case(provider, case, registry, retries=0)
    assert result.passed, "\n".join(result.reasons())


@pytest.mark.parametrize("statement", STATEMENTS, ids=lambda s: s.name)
def test_the_recorded_statements_have_not_moved(
    statement, provider: Provider, registry: OperatorRegistry
) -> None:
    """The baseline moves only on purpose.

    A recorded answer that still fails the same way is the baseline
    holding.  One that now *satisfies* the problem is progress -- and
    the gate says so, because the recording has to be refreshed before
    the baseline can move.
    """
    recorded = OUTCOMES_STATEMENTS.get(statement.name)
    assert recorded is not None, f"{statement.name} 没有记录结果"
    result = run_statement(provider, statement, registry, retries=0)
    if recorded == "satisfied":
        assert result.satisfied, "\n".join(result.reasons())
        return
    assert not result.satisfied, (
        f"{statement.name} 现在满足了题面条件（记录的是 {recorded}）——"
        "请重新录制基准（python scripts/record_fixtures.py）"
    )
