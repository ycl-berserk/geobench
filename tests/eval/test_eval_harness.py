"""The AI's answers are gated by CI.

The project's convention is that **every AI output goes through a
gate**: the figures the model produced are replayed through the same
harness the live run uses, so a change in the kernel that breaks them
is caught here rather than in front of a teacher.

The replay is **offline**: the provider below is a fake that answers
from the recorded fixtures.  The live measurement is a manual step
(``scripts/eval_ai.py``); this is the regression net under it.
"""

from __future__ import annotations

import pytest
from evals.cases import CASES
from evals.fixtures import RECORDED
from evals.harness import run_case

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
        for case in CASES:
            if case.request in user and case.name in RECORDED:
                return RECORDED[case.name]
        raise AssertionError(f"no recorded answer for this request:\n{user[:200]}")


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
    missing = [case.name for case in CASES if case.name not in RECORDED]
    assert not missing, f"这些用例还没有记录下来的答案：{missing}"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_the_recorded_answers_still_hold(
    case, provider: Provider, registry: OperatorRegistry
) -> None:
    """The recorded figure still satisfies what the problem asks for."""
    result = run_case(provider, case, registry, retries=0)
    assert result.passed, "\n".join(result.reasons())
