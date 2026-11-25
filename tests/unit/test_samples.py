"""Every sample is a claim the kernel can stand behind.

A sample that opens but whose assertion is refuted would teach the
opposite of the lesson it is named after.  This test reads every
`.geobench` in `samples/`, builds it, and proves each claim.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from geobench.dsl import parse_dsl
from geobench.evaluate import evaluate_figure
from geobench.judges import IDENTITY, JudgeRegistry, judge_relation
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry

SAMPLES = sorted((Path(__file__).resolve().parents[2] / "samples").glob("*.geobench"))


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


@pytest.mark.parametrize("path", SAMPLES, ids=lambda path: path.name)
def test_every_sample_claim_is_proved(
    path: Path, registry: OperatorRegistry
) -> None:
    source = path.read_text(encoding="utf-8")
    figure = parse_dsl(source)
    evaluate_figure(figure, registry)
    judges = JudgeRegistry()
    for relation in figure.relations:
        verdict = judge_relation(
            figure, relation.kind, list(relation.args), judges, scope=IDENTITY
        )
        assert verdict.verdict == "proved", (
            f"{path.name}: {relation.kind}{relation.args} was "
            f"{verdict.verdict}: {verdict.evidence}"
        )
