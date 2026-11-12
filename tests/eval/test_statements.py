"""The reference figures are the yardstick, so they have to be right.

Every statement in :mod:`evals.statements` carries a hand-written
figure that satisfies its conditions.  If a condition the reference
fails, then the *condition* is wrong -- not the figure -- and the whole
evaluation would be measuring the wrong thing.

So this suite checks the checks.  It is the reason the evaluation set
can be trusted: a condition that says "the tangent touches the circle"
has to be satisfied by a figure whose tangent really does.
"""

from __future__ import annotations

import pytest
from evals.statements import STATEMENTS

from geobench.dsl import parse_dsl
from geobench.evaluate import evaluate_figure, evaluate_numeric
from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def _figure(source: str, registry: OperatorRegistry):
    figure = evaluate_figure(parse_dsl(source), registry)
    evaluate_numeric(figure)
    return figure


@pytest.mark.parametrize("statement", STATEMENTS, ids=lambda s: s.name)
def test_the_reference_figure_satisfies_its_conditions(statement, registry) -> None:
    """A condition the reference fails is a condition that is wrong."""
    assert statement.reference.strip(), f"{statement.name} has no reference figure"
    figure = _figure(statement.reference, registry)
    for condition in statement.conditions:
        verdict = condition.check(figure)
        assert verdict is True, (
            f"{statement.name}: the reference figure does not satisfy "
            f"「{condition.name}」 (it answered {verdict})"
        )


@pytest.mark.parametrize("statement", STATEMENTS, ids=lambda s: s.name)
def test_the_reference_figure_has_the_named_objects(statement, registry) -> None:
    """The objects the statement names are in the reference figure."""
    figure = _figure(statement.reference, registry)
    missing = [name for name in statement.must_include if name not in figure.nodes]
    assert not missing, f"{statement.name}: the reference figure lacks {missing}"


def test_every_statement_has_conditions() -> None:
    """A statement with no condition would measure nothing."""
    empty = [statement.name for statement in STATEMENTS if not statement.conditions]
    assert not empty, f"these statements state no condition: {empty}"


def test_the_statements_are_not_all_the_same() -> None:
    """The set has to cover more than one shape of problem."""
    groups = {statement.tags[0] for statement in STATEMENTS}
    assert len(groups) >= 4, f"the statements only cover {groups}"
    assert len(STATEMENTS) >= 15, "the evaluation set is too small to say anything"


def test_every_statement_belongs_to_a_group() -> None:
    """The report sorts by group, so every statement needs one."""
    known = {"数值条件", "关系构造", "定理型", "改述"}
    unknown = {
        statement.tags[0]
        for statement in STATEMENTS
        if statement.tags[0] not in known
    }
    assert not unknown, f"these statements have no known group: {unknown}"
