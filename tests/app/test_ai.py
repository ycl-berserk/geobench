"""The model writes the DSL; the parser decides whether it is a figure.

That is the whole of the design (``docs/ai-workflow.md`` §10): the
model translates, the parser rejects. These tests pin that division of
labour down -- in particular, that a bad proposal is a *refused*
proposal and never a wrong picture.

No network is used here: the provider is a stand-in that answers with
what the test says it should.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from geobench.ai import Proposal, build_prompt, propose


class FakeProvider:
    """A provider that answers with what the test tells it to."""

    name = "fake"

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        index = min(len(self.prompts) - 1, len(self.answers) - 1)
        return self.answers[index]


GOOD = """```
点 A(0,0) B(4,0)
l = 直线(A, B)
```"""

BAD = """```
点 A(0,0)
l = 直线(A)
```"""

GARBAGE = "这个任务我不太确定怎么做。"


def test_a_good_answer_becomes_a_figure() -> None:
    provider = FakeProvider(GOOD)
    proposal = propose(provider, "画一条经过 A 和 B 的直线")
    assert proposal.ok
    assert proposal.figure is not None
    assert "l" in proposal.figure.nodes
    assert proposal.error is None


def test_a_code_fence_is_not_geometry() -> None:
    """The model likes to wrap its answer in a fence. That is not our problem."""
    provider = FakeProvider(GOOD)
    proposal = propose(provider, "画一条直线")
    assert proposal.ok
    assert "```" not in proposal.text


def test_a_bad_answer_is_refused_with_the_parser_s_own_reason() -> None:
    """The parser decides, and it says what is wrong."""
    provider = FakeProvider(BAD)
    proposal = propose(provider, "画一条直线", retries=0)
    assert not proposal.ok
    assert proposal.figure is None
    assert proposal.error
    assert "直线" in proposal.error or "参数" in proposal.error


def test_the_refusal_goes_back_to_the_model_once() -> None:
    """A model told what it got wrong usually gets it right the second time."""
    provider = FakeProvider(BAD, GOOD)
    proposal = propose(provider, "画一条直线")
    assert proposal.ok
    assert proposal.attempts == 2
    # the second attempt was told about the first failure
    assert len(provider.prompts) == 2
    assert "解析失败" in provider.prompts[1]


def test_nonsense_is_refused_rather_than_guessed_at() -> None:
    """A model that says it does not know must not become a figure."""
    provider = FakeProvider(GARBAGE)
    proposal = propose(provider, "画一条直线", retries=0)
    assert not proposal.ok
    assert proposal.figure is None


def test_the_prompt_lists_the_commands_that_exist() -> None:
    """The command list is written from the command table, so it cannot drift."""
    system, _user = build_prompt("画一条直线")
    assert "直线(" in system
    assert "圆(" in system
    # the relations are not for the model to use here
    assert "共线(" not in system


def test_the_current_figure_is_given_as_context() -> None:
    """The model should use the points that are already there."""
    _system, user = build_prompt("过 A 作垂线", current="点 A(0,0) B(4,0)\n")
    assert "A(0,0)" in user
    assert "过 A 作垂线" in user


def test_a_proposal_without_a_figure_says_so() -> None:
    proposal = Proposal(text="x", error="nope")
    assert not proposal.ok
