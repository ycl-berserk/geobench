"""The lesson format: the model writes it, the kernel can run it.

A lesson is only useful if its figure parses, its objects exist, and its
claims are relations the kernel actually has.  These tests pin those
checks; the teaching text itself is the model's business.
"""

from __future__ import annotations

import json

import pytest

from geobench.errors import GeobenchError
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry
from geobench.tutor import Lesson, answer_question, build_lesson


class FakeProvider:
    name = "fake"

    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]


def _registry() -> OperatorRegistry:
    registry = OperatorRegistry()
    register_builtins(registry)
    return registry


FIGURE = (
    "点 A(0,0) B(6,0) C(2,4)\n"
    "AB = 线段(A,B)\n"
    "M = 中点(A,B)\n"
    "隐藏 M\n"
)


def _lesson(
    *,
    figure: str = FIGURE,
    steps: list[dict[str, object]] | None = None,
) -> str:
    return json.dumps(
        {
            "title": "中点共线",
            "figure": figure,
            "goal": "证明 A、M、B 共线",
            "steps": steps
            or [
                {
                    "say": "M 是 AB 的中点，所以 M 在 AB 上。",
                    "reveal": ["M"],
                    "highlight": ["A", "B", "M"],
                    "claim": {
                        "kind": "collinear",
                        "args": ["A", "M", "B"],
                        "scope": "identity",
                    },
                    "ask": "你能看出 M 为什么在 AB 上吗？",
                }
            ],
        },
        ensure_ascii=False,
    )


def test_a_lesson_is_parsed_into_objects_the_kernel_knows() -> None:
    provider = FakeProvider([_lesson()])
    lesson = build_lesson(provider, "在 AB 上取中点 M", _registry())
    assert isinstance(lesson, Lesson)
    assert lesson.title == "中点共线"
    assert len(lesson.steps) == 1
    step = lesson.steps[0]
    assert step.reveal == ("M",)
    assert step.highlight == ("A", "B", "M")
    assert step.claim is not None
    assert step.claim.kind == "collinear"
    assert "隐藏 M" in lesson.figure


def test_a_figure_that_does_not_parse_is_retried_with_the_reason() -> None:
    broken = _lesson(figure="点 A(0,0)\nM = 不存在的命令(A)")
    provider = FakeProvider([broken, _lesson()])
    lesson = build_lesson(provider, "中点", _registry())
    assert lesson.steps
    assert "解析失败" in provider.calls[1][1]


def test_a_claim_about_an_object_that_is_not_in_the_figure_is_refused() -> None:
    bad = _lesson(
        steps=[
            {
                "say": "看 Z。",
                "claim": {
                    "kind": "collinear",
                    "args": ["A", "Z", "B"],
                    "scope": "identity",
                },
            }
        ]
    )
    provider = FakeProvider([bad, bad, bad])
    with pytest.raises(GeobenchError, match="Z"):
        build_lesson(provider, "中点", _registry())


def test_a_false_claim_is_sent_back_instead_of_taught() -> None:
    """A lesson with a claim the kernel refutes is not a lesson."""
    figure = "点 A(0,0) B(6,0) C(2,4)\nAB = 线段(A,B)\nBC = 线段(B,C)\n"
    bad = _lesson(
        figure=figure,
        steps=[
            {
                "say": "AB 和 BC 垂直。",
                "claim": {
                    "kind": "perpendicular",
                    "args": ["AB", "BC"],
                    "scope": "identity",
                },
            }
        ],
    )
    provider = FakeProvider([bad, bad, bad])
    with pytest.raises(GeobenchError, match="内核判为"):
        build_lesson(provider, "看一个假命题", _registry())
    # The retry carries the kernel's reason, not just "try again".
    assert "refuted" in provider.calls[1][1]


def test_a_reply_can_point_reveal_and_construct() -> None:
    provider = FakeProvider([_lesson()])
    lesson = build_lesson(provider, "中点", _registry())
    answer = json.dumps(
        {
            "say": "把 AM 连起来看。",
            "highlight": ["A", "M"],
            "reveal": ["M"],
            "construct": [
                {"op": "line.free", "args": ["A", "M"], "id": "AM"}
            ],
            "claim": {
                "kind": "collinear",
                "args": ["A", "M", "B"],
                "scope": "identity",
            },
        },
        ensure_ascii=False,
    )
    reply = answer_question(
        FakeProvider([answer]),
        lesson,
        0,
        "为什么要连 AM？",
        lesson.figure,
        [("学生", "为什么要连 AM？")],
        _registry(),
    )
    assert reply.say.startswith("把 AM")
    assert reply.reveal == ("M",)
    assert reply.construct[0].id == "AM"
    assert reply.claim is not None


def test_a_reply_with_an_unknown_object_is_refused_before_the_canvas() -> None:
    provider = FakeProvider([_lesson()])
    lesson = build_lesson(provider, "中点", _registry())
    bad = json.dumps({"say": "看 Z。", "highlight": ["Z"]}, ensure_ascii=False)
    with pytest.raises(GeobenchError, match="Z"):
        answer_question(
            FakeProvider([bad]),
            lesson,
            0,
            "看哪里？",
            lesson.figure,
            [],
            _registry(),
        )
