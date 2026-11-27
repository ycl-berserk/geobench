"""The model reads a sentence; the kernel decides what is true.

The claim translator is allowed to be wrong about the geometry, because
it never says whether a claim holds. It only fills in a relation id and
the objects the sentence named; the studio checks those against the
figure and the kernel judges them. These tests pin that division down.
"""

from __future__ import annotations

import pytest

from geobench.ai import Claim, interpret_claims
from geobench.errors import GeobenchError
from geobench.judges import IDENTITY, INSTANCE


class FakeProvider:
    """A provider that answers from a fixed string."""

    name = "fake"

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.answer


def test_a_sentence_becomes_the_relation_it_names() -> None:
    provider = FakeProvider(
        '{"claims": [{"kind": "collinear", "args": ["A", "M", "B"],'
        ' "scope": "instance"}]}'
    )
    claims = interpret_claims(
        provider, "A、M、B 共线吗？", "点 A(0,0) B(6,0)\nM = 中点(A, B)\n"
    )
    assert claims == [Claim("collinear", ("A", "M", "B"), INSTANCE)]
    system, user = provider.calls[0]
    # The catalogue is generated, and the figure is given as context.
    assert "collinear" in system
    assert "A、M、B 共线吗？" in user
    assert "M = 中点(A, B)" in user


def test_the_scope_defaults_to_proof() -> None:
    provider = FakeProvider(
        '{"claims": [{"kind": "parallel", "args": ["AB", "CD"]}]}'
    )
    claims = interpret_claims(provider, "AB 和 CD 平行吗？")
    assert claims[0].scope == IDENTITY


def test_a_code_fence_and_a_sentence_before_the_json_are_tolerated() -> None:
    provider = FakeProvider(
        "好的，我把它翻译成关系：\n"
        "```json\n"
        '{"claims": [{"kind": "collinear", "args": ["A", "B", "C"],'
        ' "scope": "identity"}]}\n'
        "```\n"
    )
    claims = interpret_claims(provider, "证明 A、B、C 共线")
    assert claims == [Claim("collinear", ("A", "B", "C"), IDENTITY)]


def test_a_refusal_is_carried_back_to_the_teacher() -> None:
    provider = FakeProvider('{"error": "没有说清是哪三个点"}')
    with pytest.raises(GeobenchError, match="没有说清"):
        interpret_claims(provider, "它们共线吗？")


def test_an_answer_that_is_not_json_is_an_error_not_a_guess() -> None:
    provider = FakeProvider("它们共线。")
    with pytest.raises(GeobenchError, match="JSON"):
        interpret_claims(provider, "它们共线吗？")


def test_too_many_claims_in_one_sentence_are_refused() -> None:
    item = '{"kind": "collinear", "args": ["A", "B", "C"]}'
    provider = FakeProvider('{"claims": [' + ", ".join([item] * 9) + "]}")
    with pytest.raises(GeobenchError, match="太多"):
        interpret_claims(provider, "问很多条")
