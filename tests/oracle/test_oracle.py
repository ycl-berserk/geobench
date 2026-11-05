"""The oracle gate: every operator is cross-checked against an independent implementation.

This is the project's most important test. An operator that disagrees with
its oracle fails the build, and an operator without a full fixture battery
fails the build too (docs/spec.md section 5.3).
"""

from __future__ import annotations

import pytest
from harness import (
    MIN_CONFIGS,
    MIN_DEGENERATE,
    MIN_NON_NORMAL,
    check_operator,
    coverage_report,
    load_fixtures,
    uncovered_operators,
)

from geobench.operators import register_builtins
from geobench.registry import OperatorRegistry


@pytest.fixture(scope="module")
def registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    register_builtins(reg)
    return reg


def test_every_operator_matches_its_oracle(registry: OperatorRegistry) -> None:
    failures: list[str] = []
    for op_id in registry.ids():
        if op_id in {"point.free", "circle.free"}:
            continue
        for mismatch in check_operator(op_id, registry, None):
            failures.append(str(mismatch))
    assert not failures, "oracle mismatches:\n" + "\n".join(failures)


def test_every_operator_has_a_full_fixture_battery(registry: OperatorRegistry) -> None:
    missing = uncovered_operators(registry)
    assert not missing, f"operators without a full oracle battery: {missing}"


def test_fixture_batteries_meet_the_minimum(registry: OperatorRegistry) -> None:
    for op_id in registry.ids():
        if op_id in {"point.free", "circle.free"}:
            continue
        fixtures = load_fixtures(op_id)
        degenerate = sum(1 for f in fixtures if f.kind == "degenerate")
        non_normal = sum(1 for f in fixtures if f.kind != "normal")
        assert len(fixtures) >= MIN_CONFIGS, f"{op_id}: only {len(fixtures)} fixtures"
        assert non_normal >= MIN_NON_NORMAL, f"{op_id}: only {non_normal} non-normal fixtures"
        spec = registry.lookup(op_id)
        if spec.degenerate_when:
            assert degenerate >= MIN_DEGENERATE, (
                f"{op_id}: declares degenerate_when but has only {degenerate} "
                "degenerate fixtures"
            )


def test_degenerate_fixtures_expect_an_error(registry: OperatorRegistry) -> None:
    for op_id in registry.ids():
        if op_id in {"point.free", "circle.free"}:
            continue
        for fixture in load_fixtures(op_id):
            if fixture.kind == "degenerate":
                assert fixture.expect == "error", f"{op_id}: degenerate fixture expects a value"


def test_coverage_report_is_generated(registry: OperatorRegistry) -> None:
    report = coverage_report(registry)
    assert "point.midpoint" in report
    assert "point.circumcenter" in report
