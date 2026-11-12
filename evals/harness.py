"""Run the cases, and say which ones the model got right.

The harness is deliberately independent of the studio: it takes a
provider, a case and a registry, and returns a verdict about the
figure.  That is what makes it usable twice -- in CI with a **fake**
provider (never the network), and by hand against a real service.

There are two kinds of question, and they are kept apart on purpose:

- the **cases** (:mod:`evals.cases`) measure the contract: does the
  model know our language, our commands and our conventions?
- the **statements** (:mod:`evals.statements`) measure the product:
  type a problem, get a figure that satisfies it?

The expectations are checked on the **figure**, not on the text: a
model may write the same figure in a different order.  What is checked
is that the objects the problem names are there, that the claims hold
**in the drawn configuration**, and that nothing in the figure has no
value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from evals.cases import Case
from evals.statements import Statement
from geobench.ai import Problem, Provider, propose
from geobench.dsl import parse_dsl
from geobench.dsl.errors import DSLParseError
from geobench.errors import GeobenchError
from geobench.evaluate import evaluate_figure, numeric_coords
from geobench.judges import INSTANCE, PROVED, JudgeRegistry, judge_relation
from geobench.model import Figure
from geobench.registry import OperatorRegistry


@dataclass(frozen=True)
class CaseResult:
    """What came back, and how it held up."""

    case: Case
    text: str
    parsed: bool
    error: str = ""
    problems: tuple[Problem, ...] = ()
    missing: tuple[str, ...] = ()
    """Objects the problem names that the figure does not have."""

    unwanted: tuple[str, ...] = ()
    """Objects the figure has that it should not."""

    unproved: tuple[str, ...] = ()
    """Claims the drawn figure does not satisfy."""

    substituted: tuple[str, ...] = ()
    """Claims the drawn figure satisfies that it should not -- the model
    quietly drew something else."""

    refused: bool = False
    """The model said the request cannot be done."""

    angle_wrong: tuple[str, ...] = ()
    """The coordinates do not satisfy the condition the problem states."""

    segments: int = 0
    """How many segments the figure draws."""

    attempts: int = 1

    @property
    def passed(self) -> bool:
        """Is this a figure a teacher could hand out?"""
        if self.case.expect_wall:
            # The request cannot be done.  What is being measured is
            # that the kernel **caught it** -- that the software did not
            # quietly hand out a figure that is not what was asked for.
            # Saying "it cannot be done" counts too.
            if self.substituted:
                return False
            return self.parsed and (bool(self.problems) or self.refused)
        return (
            self.parsed
            and not self.problems
            and not self.missing
            and not self.unwanted
            and not self.unproved
            and not self.substituted
            and not self.angle_wrong
            and self.segments >= self.case.min_segments
        )

    def reasons(self) -> list[str]:
        """Why it failed, in a sentence each."""
        out: list[str] = []
        if not self.parsed:
            out.append(f"解析失败：{self.error}")
        for problem in self.problems:
            out.append(problem.to_text())
        for name in self.missing:
            out.append(f"少了 {name}")
        for name in self.unwanted:
            out.append(f"多了 {name}")
        for claim in self.unproved:
            out.append(f"这条不成立：{claim}")
        for claim in self.substituted:
            out.append(f"这条**不该**成立（模型换了图）：{claim}")
        if self.refused:
            out.append("模型说做不到")
        for angle in self.angle_wrong:
            out.append(f"角度不对：{angle}")
        if self.segments < self.case.min_segments:
            out.append(f"只画了 {self.segments} 条线段，题目至少要 {self.case.min_segments} 条")
        return out


def run_case(
    provider: Provider,
    case: Case,
    registry: OperatorRegistry,
    retries: int = 2,
) -> CaseResult:
    """Ask the model for this figure, and check it."""
    proposal = propose(provider, case.request, "", registry, retries=retries)
    if not proposal.ok:
        return CaseResult(
            case=case,
            text=proposal.text,
            parsed=False,
            error=proposal.error or "the model said nothing usable",
            attempts=proposal.attempts,
        )
    figure = evaluate_figure(proposal.figure, registry)
    refused = not figure.nodes and "#" in proposal.text
    if case.expect_wall:
        # The point of this case is the wall, not the figure.
        unproved: tuple[str, ...] = ()
        missing: tuple[str, ...] = ()
        unwanted: tuple[str, ...] = ()
        substituted = (
            () if refused else _check_claims(case.must_not_relate, proposal.text, registry)
        )
    else:
        missing = tuple(name for name in case.must_include if name not in figure.nodes)
        unwanted = tuple(name for name in case.must_not if name in figure.nodes)
        unproved = _check_claims(case.must_relate, proposal.text, registry)
        substituted = _check_claims(case.must_not_relate, proposal.text, registry)
    angle_wrong = _check_angles(case, figure)
    segments = sum(1 for node in figure.nodes.values() if node.kind == "segment")
    return CaseResult(
        case=case,
        text=proposal.text,
        parsed=True,
        problems=tuple(proposal.problems),
        missing=missing,
        unwanted=unwanted,
        unproved=unproved,
        substituted=substituted,
        refused=refused,
        angle_wrong=angle_wrong,
        segments=segments,
        attempts=proposal.attempts,
    )


def _check_claims(
    claims: tuple[tuple[str, tuple[str, ...]], ...], text: str, registry: OperatorRegistry
) -> tuple[str, ...]:
    """Do these claims hold in the drawn figure?

    The claim is written the way the DSL writes it, so it is checked
    the way a teacher would check it: the assertion is appended to the
    figure's own text, parsed by the same parser, and judged in the
    drawn configuration.
    """
    if not claims:
        return ()
    judges = JudgeRegistry()
    bad: list[str] = []
    for name, args in claims:
        line = f"断言 {name}({', '.join(args)})"
        try:
            extended = parse_dsl(text + "\n" + line)
        except (GeobenchError, DSLParseError) as exc:
            bad.append(f"{line}（写不出来：{exc}）")
            continue
        if not extended.relations:
            bad.append(f"{line}（没被认成断言）")
            continue
        relation = extended.relations[-1]
        # The judge reads the exact path, so the figure has to be
        # evaluated first -- a figure that was only parsed has no
        # coordinates yet.
        evaluated = evaluate_figure(extended, registry)
        verdict = judge_relation(
            evaluated, relation.kind, list(relation.args), judges, scope=INSTANCE
        )
        if verdict.verdict != PROVED:
            bad.append(f"{line}（{verdict.verdict}）")
    return tuple(bad)


def _check_angles(case: Case, figure: Figure) -> tuple[str, ...]:
    """Do the coordinates satisfy the condition the problem states?

    "锐角三角形" is a condition on the **coordinates**, and a model
    that draws an obtuse triangle has not drawn the figure the problem
    is about -- no amount of correct construction makes it right.
    """
    wrong: list[str] = []
    if case.acute and not _is_acute(figure, case.acute):
        wrong.append(f"{case.acute} 不是锐角三角形")
    if case.right_at:
        first, vertex, third = case.right_at
        if not _is_right_at(figure, first, vertex, third):
            wrong.append(f"{vertex} 处的角不是直角")
    return tuple(wrong)


# -- the statements ---------------------------------------------------------


@dataclass(frozen=True)
class StatementResult:
    """What came back for a problem statement, and how it held up.

    Three outcomes are kept apart, because they are three different
    failures:

    - **unmet** -- the figure *contradicts* the statement (the sides
      are not the lengths the statement says);
    - **unanswered** -- the figure does not even have the objects the
      statement names, so it never addressed the question;
    - **refused** -- the model said the request cannot be done.
    """

    statement: Statement
    text: str
    parsed: bool
    error: str = ""
    unmet: tuple[str, ...] = ()
    """Conditions the figure does not satisfy."""

    unanswered: tuple[str, ...] = ()
    """Conditions that could not be checked -- an object is missing."""

    missing: tuple[str, ...] = ()
    """Objects the statement names that the figure does not have."""

    problems: tuple[Problem, ...] = ()
    refused: bool = False
    attempts: int = 1

    @property
    def satisfied(self) -> bool:
        """Is this a figure a teacher could hand out?"""
        return (
            self.parsed
            and not self.unmet
            and not self.unanswered
            and not self.missing
            and not self.problems
        )

    @property
    def outcome(self) -> str:
        """One word for what happened -- this is what CI compares."""
        if not self.parsed:
            return "parse-failure"
        if self.refused:
            return "refused"
        if self.satisfied:
            return "satisfied"
        return "unsatisfied"

    def reasons(self) -> list[str]:
        """Why it failed, in a sentence each."""
        out: list[str] = []
        if not self.parsed:
            out.append(f"解析失败：{self.error}")
        if self.refused:
            out.append("模型说做不到")
        for problem in self.problems:
            out.append(problem.to_text())
        for name in self.unmet:
            out.append(f"条件不满足：{name}")
        for name in self.unanswered:
            out.append(f"条件没法验（缺对象）：{name}")
        for name in self.missing:
            out.append(f"少了 {name}")
        return out


def run_statement(
    provider: Provider,
    statement: Statement,
    registry: OperatorRegistry,
    retries: int = 2,
) -> StatementResult:
    """Ask the model for this figure, and check it against the statement."""
    proposal = propose(provider, statement.request, "", registry, retries=retries)
    if not proposal.ok:
        return StatementResult(
            statement=statement,
            text=proposal.text,
            parsed=False,
            error=proposal.error or "the model said nothing usable",
            attempts=proposal.attempts,
        )
    figure = evaluate_figure(proposal.figure, registry)
    unmet: list[str] = []
    unanswered: list[str] = []
    for condition in statement.conditions:
        try:
            verdict = condition.check(figure)
        except Exception:  # pragma: no cover - a check that cannot run
            verdict = None
        if verdict is True:
            continue
        if verdict is None:
            unanswered.append(condition.name)
        else:
            unmet.append(condition.name)
    missing = tuple(name for name in statement.must_include if name not in figure.nodes)
    refused = not figure.nodes and "#" in proposal.text
    return StatementResult(
        statement=statement,
        text=proposal.text,
        parsed=True,
        unmet=tuple(unmet),
        unanswered=tuple(unanswered),
        missing=missing,
        problems=tuple(proposal.problems),
        refused=refused,
        attempts=proposal.attempts,
    )


@dataclass
class StatementReport:
    """The whole run over the statements, and what it says."""

    results: list[StatementResult] = field(default_factory=list)

    @property
    def satisfied(self) -> int:
        return sum(1 for result in self.results if result.satisfied)

    @property
    def total(self) -> int:
        return len(self.results)

    def by_group(self) -> dict[str, tuple[int, int]]:
        """How each kind of statement did: (satisfied, total)."""
        counts: dict[str, list[int]] = {}
        for result in self.results:
            group = result.statement.tags[0] if result.statement.tags else "其他"
            entry = counts.setdefault(group, [0, 0])
            entry[1] += 1
            if result.satisfied:
                entry[0] += 1
        return {group: (value[0], value[1]) for group, value in sorted(counts.items())}

    def summary(self) -> str:
        """The report, in lines."""
        lines = []
        for result in self.results:
            mark = "PASS" if result.satisfied else "FAIL"
            group = result.statement.tags[0] if result.statement.tags else ""
            lines.append(f"[{mark}] {result.statement.name}  ({group})")
            for reason in result.reasons():
                lines.append(f"        · {reason}")
        lines.append("")
        for group, (passed, total) in self.by_group().items():
            lines.append(f"{group}：{passed}/{total}")
        lines.append("")
        lines.append(f"{self.satisfied}/{self.total} 满足题面条件")
        return "\n".join(lines)


def run_all_statements(
    provider: Provider,
    registry: OperatorRegistry,
    statements: tuple[Statement, ...] | None = None,
    retries: int = 2,
) -> StatementReport:
    """Run every statement, and report."""
    from evals.statements import STATEMENTS

    report = StatementReport()
    for statement in statements if statements is not None else STATEMENTS:
        report.results.append(run_statement(provider, statement, registry, retries=retries))
    return report


def _coordinates(figure: Figure, name: str) -> tuple[float, float] | None:
    try:
        return numeric_coords(figure, name)
    except GeobenchError:
        return None


def _is_acute(figure: Figure, names: tuple[str, str, str]) -> bool:
    points = [_coordinates(figure, name) for name in names]
    if any(point is None for point in points):
        return False
    first, second, third = points  # type: ignore[misc]
    for a, b, c in (
        (first, second, third),
        (second, third, first),
        (third, first, second),
    ):
        side_a = _distance(b, c)
        side_b = _distance(a, c)
        side_c = _distance(a, b)
        if side_a**2 >= side_b**2 + side_c**2:
            return False
    return True


def _is_right_at(figure: Figure, first: str, vertex: str, third: str) -> bool:
    a = _coordinates(figure, first)
    b = _coordinates(figure, vertex)
    c = _coordinates(figure, third)
    if a is None or b is None or c is None:
        return False
    left = (a[0] - b[0], a[1] - b[1])
    right = (c[0] - b[0], c[1] - b[1])
    dot = left[0] * right[0] + left[1] * right[1]
    return math.isclose(dot, 0.0, abs_tol=1e-9)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class Report:
    """The whole run, and what it says."""

    results: list[CaseResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    def summary(self) -> str:
        """The report, in lines."""
        lines = []
        for result in self.results:
            mark = "PASS" if result.passed else "FAIL"
            lines.append(f"[{mark}] {result.case.name}  (attempts={result.attempts})")
            for reason in result.reasons():
                lines.append(f"        · {reason}")
        lines.append("")
        lines.append(f"{self.passed}/{self.total} 通过")
        return "\n".join(lines)


def run_all(
    provider: Provider,
    registry: OperatorRegistry,
    cases: tuple[Case, ...] | None = None,
    retries: int = 2,
) -> Report:
    """Run every case, and report."""
    from evals.cases import CASES

    report = Report()
    for case in cases if cases is not None else CASES:
        report.results.append(run_case(provider, case, registry, retries=retries))
    return report


__all__ = [
    "CaseResult",
    "Report",
    "StatementReport",
    "StatementResult",
    "run_all",
    "run_all_statements",
    "run_case",
    "run_statement",
]
