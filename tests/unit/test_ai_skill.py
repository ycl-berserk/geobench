"""The model has to be able to learn from what it is told.

The channel is only as good as its feedback: a model that is told
"unknown command 'A'" will write ``A(0,0)`` again, and a model that is
told "a free point is written 点 A(x, y)" will not.

So there are three things here:

- the **error teaches** -- it says what to write instead;
- the **kernel judges the figure**, not just the text, so a figure that
  cannot exist is caught;
- and the **loop gives the model another try**, with the reason.
"""

from __future__ import annotations

import pytest

from geobench.ai import check_figure, propose
from geobench.dsl import parse_dsl
from geobench.dsl.errors import DSLParseError
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


class ScriptedProvider:
    """A provider that answers with a fixed list of texts, in order."""

    name = "scripted"

    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.prompts: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        index = min(len(self.prompts) - 1, len(self.answers) - 1)
        return self.answers[index]


# -- the error teaches ------------------------------------------------------


def test_a_free_point_without_the_keyword_says_what_to_write() -> None:
    """The mistake the model made most often, named exactly."""
    with pytest.raises(DSLParseError) as failure:
        parse_dsl("A(0,0) B(5,0)")
    message = str(failure.value)
    assert "点" in message, message
    assert "A" in message, message


def test_an_unknown_command_suggests_the_one_it_meant() -> None:
    """A name that is nearly a command is nearly always a typo of one."""
    with pytest.raises(DSLParseError) as failure:
        parse_dsl("点 A(0,0) B(4,0)\nM = Midpointt(A,B)")
    message = str(failure.value)
    assert "Midpoint" in message, message


def test_a_chinese_typo_is_suggested_too() -> None:
    """The suggestion speaks the language that was typed."""
    with pytest.raises(DSLParseError) as failure:
        parse_dsl("点 A(0,0) B(4,0)\nM = 中点t(A,B)")
    message = str(failure.value)
    assert "中点" in message, message


def test_a_name_that_is_nothing_like_a_command_gets_no_suggestion() -> None:
    """A guess is worse than no guess.

    The comparison is an exact edit distance, so a name that is far
    from every command gets no suggestion at all -- the error says only
    that the command is unknown.
    """
    with pytest.raises(DSLParseError) as failure:
        parse_dsl("点 A(0,0) B(4,0)\nM = zzzzqqq(A,B)")
    message = str(failure.value)
    assert "你是不是想写" not in message, message


# -- the DSL was broken, and now works --------------------------------------


def test_the_relation_point_in_can_be_written() -> None:
    """点在 is one command, not 点 plus 在.

    The lexer used to split the run at the 点 keyword, which left one
    of the seventeen relations unwritable.
    """
    figure = parse_dsl(
        """
点 A(0,0) B(4,0) C(1,3)
w = 外接圆(A, B, C)
P = 圆上的点(w, 1/4)
断言 点在(P, w)
"""
    )
    assert [relation.kind for relation in figure.relations] == ["point_in"]


def test_two_drawn_segments_can_be_compared() -> None:
    """相等(AB, AC) is how a paper writes it, and it has to work.

    A segment that was *drawn* did not remember its two ends, so it
    could not be opened up -- while the same segment written as two
    letters could.
    """
    figure = parse_dsl(
        """
点 A(0,3) B(-2,0) C(2,0)
AB = 线段(A, B)
AC = 线段(A, C)
断言 相等(AB, AC)
"""
    )
    assert [(r.kind, r.args) for r in figure.relations] == [
        ("equal_length", ["A", "B", "A", "C"])
    ]


# -- the kernel judges the figure -------------------------------------------


def test_an_object_that_cannot_exist_is_caught(registry: OperatorRegistry) -> None:
    """The intersection of two lines that are always parallel.

    The point does not exist, and a figure that pretends it does is
    exactly what a teacher would bounce.
    """
    figure = parse_dsl(
        """
点 A(2,3) B(0,0) C(5,0)
H = 垂心(A, B, C)
D = 中点(B, C)
bc = 直线(B, C)
d = 垂直(D, bc)
ah = 直线(A, H)
P = 交点(d, ah)
"""
    )
    problems = check_figure(figure, registry)
    assert problems, "a point that cannot exist was not caught"
    assert "P" in problems[0].subject


def test_a_claim_the_figure_does_not_satisfy_is_caught(registry: OperatorRegistry) -> None:
    """A wrong assertion is caught in the drawn configuration."""
    figure = parse_dsl(
        """
点 A(0,0) B(4,0) C(1,3)
O = 外心(A, B, C)
断言 外心(A, B, C, O)
"""
    )
    problems = check_figure(figure, registry)
    assert problems, "a false claim was not caught"
    assert problems[0].kind == "refuted"


# -- the loop gives another try ---------------------------------------------


def test_a_parse_error_goes_back_to_the_model(registry: OperatorRegistry) -> None:
    """The model is told what the parser objected to."""
    provider = ScriptedProvider(["A(0,0) B(5,0)", "点 A(0,0) B(5,0)"])
    proposal = propose(provider, "画一条线段", "", registry, retries=1)
    assert proposal.ok
    assert proposal.attempts == 2
    assert "解析失败" in provider.prompts[1]


def test_a_broken_figure_goes_back_to_the_model(registry: OperatorRegistry) -> None:
    """And so is a figure the kernel does not believe.

    A tangent from a point *inside* the circle has no value: there is no
    tangent from there.  The figure is valid code, so only the kernel can
    see it -- and it is exactly what the model has to be told.
    """
    provider = ScriptedProvider(
        [
            "点 O(0,0) A(2,0) P(1,0)\nc = 圆(O, A)\nt = 切线(P, c)",
            "点 O(0,0) A(2,0)\nc = 圆(O, A)\nP = 圆上的点(c, 1/4)\nt = 切线(P, c)",
        ]
    )
    proposal = propose(provider, "作一条切线", "", registry, retries=1)
    assert proposal.ok
    assert proposal.attempts == 2
    assert "内核查出图有问题" in provider.prompts[1]


def test_a_clean_figure_is_not_asked_again(registry: OperatorRegistry) -> None:
    """One try is enough when there is nothing to fix."""
    provider = ScriptedProvider(["点 A(0,0) B(5,0)"])
    proposal = propose(provider, "画一条线段", "", registry, retries=2)
    assert proposal.ok
    assert proposal.attempts == 1
    assert proposal.clean
    assert len(provider.prompts) == 1
