"""A lesson on the canvas: the model plans, the kernel checks.

A geometry problem is not a picture and not a paragraph; it is a
construction plus a chain of facts about it.  That is exactly what this
project already has -- a DSL that builds the construction and judges
that decide the facts -- so the tutor is built on those two, not beside
them.

The division of labour is the same one the rest of the AI channel uses
(``docs/ai-workflow.md``):

- the **model** reads the problem, proposes a figure, and writes the
  teaching steps;
- the **parser** decides whether the figure exists;
- the **kernel** decides whether each geometric claim is true.

The model is allowed to be wrong.  A wrong figure is rejected before it
reaches the canvas; a wrong claim is shown to the student as "内核没有
通过", not silently taught as a proof.  What the model says *about* the
proof is still its own explanation -- a proof assistant can check the
facts, not the rhetoric -- and the prompt says so.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from geobench.ai import (
    Claim,
    OpenAICompatibleProvider,
    Provider,
    check_figure,
    command_list,
    json_object,
    relation_list,
    resource,
)
from geobench.commands import COMMANDS, JUDGEMENT
from geobench.dsl import parse_dsl
from geobench.dsl.errors import DSLParseError
from geobench.errors import GeobenchError, RegistryError
from geobench.judges import (
    IDENTITY,
    INSTANCE,
    REFUTED,
    UNDECIDED,
    JudgeRegistry,
    Verdict,
    judge_relation,
)
from geobench.model import Figure
from geobench.registry import OperatorRegistry

__all__ = [
    "ConstructOp",
    "Lesson",
    "TutorReply",
    "TutorStep",
    "answer_question",
    "build_lesson",
]

#: The two prompts live with the other AI text: they are data, and the
#: packaged app reads the same files the checkout does.
_LESSON_PROMPT = resource("prompts/geometry-tutor.md")
_REPLY_PROMPT = resource("prompts/geometry-tutor-reply.md")

#: How many steps a lesson may have.  Three is the shortest thing that
#: is a proof rather than an answer; twelve is already a lecture.
_MIN_STEPS = 1
_MAX_STEPS = 12

#: What each slot of a relation accepts.  This mirrors the judgement
#: contract in the parser; it is repeated here so the tutor can reject a
#: mistranslation before the app ever shows it.
_SLOT_FITS: dict[str, frozenset[str]] = {
    "point": frozenset({"point"}),
    "line": frozenset({"line", "segment", "ray"}),
    "circle": frozenset({"circle"}),
    "any": frozenset({"line", "segment", "ray", "circle"}),
}

#: What a refutation usually means, in words the model can act on.  A
#: page of symbolic evidence is not feedback; "the angles may be
#: supplementary" is.
_CLAIM_HINTS: dict[str, str] = {
    "angle_equal": (
        "两个角在一般摆放下不一定相等（同弦圆周角在弦的两侧会互补）。"
        "如果这一步是角度推理，请**直接删掉这条 claim、保留 say**，"
        "不要再换另一条 angle_equal；或者改用等长/垂直/共圆等真恒等式。"
    ),
    "equal_length": (
        "这两条线段在一般摆放下不一定相等。检查图形是否把条件画成了构造"
        "（圆上的点 / 中点 / 交点分支），或换一条所有摆放下都成立的 claim。"
    ),
    "concyclic": (
        "这四点不一定共圆。检查外接圆/圆上的点/交点分支是否选对。"
    ),
    "point_in": (
        "这个点不一定在对象上。检查交点分支、圆上的点或线上的点。"
    ),
    "collinear": (
        "这三点不一定共线。检查中点/交点/垂足等构造，不要只摆位置。"
    ),
    "perpendicular": (
        "这两条线不一定垂直。检查垂足/垂心/交点分支是否选对。"
    ),
    "parallel": (
        "这两条线不一定平行。检查平行构造，不要只摆成平行。"
    ),
    "midpoint_of": (
        "这个点不一定是中点。检查中点构造。"
    ),
    "ratio_equal": (
        "两组线段的比例不一定相等。检查 claim 的分组和图形构造。"
    ),
}


@dataclass(frozen=True)
class ConstructOp:
    """One auxiliary object the tutor adds while explaining."""

    op: str
    args: tuple[str, ...]
    id: str


@dataclass(frozen=True)
class TutorStep:
    """One step of the lesson: what to say, what to show, what to check."""

    say: str
    reveal: tuple[str, ...] = ()
    highlight: tuple[str, ...] = ()
    claim: Claim | None = None
    ask: str = ""


@dataclass(frozen=True)
class Lesson:
    """A problem, its figure, and the steps that explain it."""

    title: str
    problem: str
    figure: str
    goal: str
    steps: tuple[TutorStep, ...]


@dataclass(frozen=True)
class TutorReply:
    """One answer to a student's question, with optional actions."""

    say: str
    highlight: tuple[str, ...] = ()
    reveal: tuple[str, ...] = ()
    construct: tuple[ConstructOp, ...] = ()
    claim: Claim | None = None
    ask: str = ""


# -- the catalogue ---------------------------------------------------------


def _relation_specs() -> dict[str, tuple[int, tuple[str, ...]]]:
    """Every relation the kernel can judge: arity and per-slot kinds."""
    specs: dict[str, tuple[int, tuple[str, ...]]] = {}
    for command in COMMANDS:
        if command.kind != JUDGEMENT or not command.implemented:
            continue
        kinds = command.arg_kinds or ("point",) * command.arity
        specs[command.id] = (command.arity, kinds)
    return specs


def _prompt(path: Path, registry: OperatorRegistry) -> str:
    template = path.read_text(encoding="utf-8")
    return template.replace("{commands}", command_list(registry)).replace(
        "{relations}", relation_list()
    )


def _with_budget(provider: Provider, tokens: int) -> Provider:
    """A lesson is longer than a figure; do not let the default cap cut it.

    The OpenAI-compatible client defaults to 700 output tokens, which is
    enough for a few dozen lines of DSL but not for a figure plus five
    explanations.  A truncated answer is invalid JSON, and the retry
    would ask for the same thing with the same cap.
    """
    if isinstance(provider, OpenAICompatibleProvider):
        return replace(provider, max_tokens=max(provider.max_tokens, tokens))
    return provider


def _node_kinds(figure: Figure) -> dict[str, str]:
    return {node_id: node.kind for node_id, node in figure.nodes.items()}


def _names(raw: object, node_kinds: dict[str, str], field: str) -> tuple[str, ...]:
    """A list of object names that must all exist in the figure."""
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(name, str) for name in raw):
        raise GeobenchError(f"{field} 必须是对象名字的列表")
    names = [str(name) for name in raw]
    for name in names:
        if name not in node_kinds:
            raise GeobenchError(f"{field} 里的 {name} 不在图里")
    return tuple(names)


def _claim(raw: object, node_kinds: dict[str, str]) -> Claim | None:
    """One relation in the kernel's own terms."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise GeobenchError("claim 必须是一个对象")
    kind = str(raw.get("kind") or "").strip()
    specs = _relation_specs()
    if kind not in specs:
        raise GeobenchError(f"claim 里的关系 {kind!r} 内核不认识")
    arity, slots = specs[kind]
    args = raw.get("args")
    if not isinstance(args, list) or len(args) != arity:
        raise GeobenchError(f"{kind} 需要 {arity} 个对象")
    if not all(isinstance(arg, str) for arg in args):
        raise GeobenchError(f"{kind} 的对象名字必须是文字")
    names = [str(arg) for arg in args]
    for name, slot in zip(names, slots, strict=True):
        node_kind = node_kinds.get(name)
        if node_kind is None:
            raise GeobenchError(f"{kind} 里的 {name} 不在图里")
        if node_kind not in _SLOT_FITS.get(slot, frozenset({slot})):
            raise GeobenchError(f"{kind} 的 {name} 类型不对（需要 {slot}）")
    scope = str(raw.get("scope") or IDENTITY)
    if scope not in (IDENTITY, INSTANCE):
        scope = IDENTITY
    return Claim(kind=kind, args=tuple(names), scope=scope)


def _intersection_lint(figure: Figure) -> None:
    """Catch the most common DSL mistake before judging any claim.

    ``交点(直线, 圆, 1)`` is a *branch number*, not "the other point".
    A model that means the second intersection often writes ``1`` and
    gets the point the line was drawn through -- the figure then looks
    plausible and every claim about it is false.  Saying exactly that is
    more useful than a page of polynomial evidence.
    """
    placements = {
        node.id: node.placement
        for node in figure.nodes.values()
        if node.kind == "point" and node.placement is not None
    }
    intersections = {
        "point.intersect_line_circle",
        "point.intersect_lines",
        "point.intersect_circles",
    }
    for node in figure.nodes.values():
        if node.op not in intersections or node.placement is None:
            continue
        position = node.placement
        # The known points are the defining points of the objects the
        # intersection was built from; one level is enough for the DSL's
        # lines, segments and circles.
        defining: set[str] = set()
        for arg in node.args[:2]:
            obj = figure.nodes.get(arg)
            if obj is None:
                continue
            for part in obj.args:
                if part in figure.nodes and figure.nodes[part].kind == "point":
                    defining.add(part)
        for known in defining:
            if known == node.id:
                continue
            if placements.get(known) == position:
                raise GeobenchError(
                    f"`{node.id} = 交点(...)` 选到了已知点 {known}。"
                    "如果你要的是另一个交点，请写 `交点(直线, 圆, 另一交点)`；"
                    "0/1 是分支号，不保证是另一个。"
                )


def _claim_hint(claim: Claim, verdict: Verdict) -> str:
    if verdict.verdict == UNDECIDED:
        return (
            "内核在预算内没有判定这一条；请简化图形、减少辅助线，"
            "或删掉这条 claim 用文字解释。"
        )
    return _CLAIM_HINTS.get(
        claim.kind,
        "这条 claim 在一般摆放下不成立；请检查图形是否把条件画成了构造，"
        "或删掉它用文字解释。",
    )


def _lesson_from(
    data: object,
    problem: str,
    registry: OperatorRegistry,
    progress: Callable[[str], None] | None = None,
) -> Lesson:
    """Turn the model's JSON into a lesson, or say exactly what is wrong."""
    if not isinstance(data, dict):
        raise GeobenchError("模型没有返回一个 JSON 对象")
    title = str(data.get("title") or "一道几何题").strip()
    goal = str(data.get("goal") or "").strip()
    figure_text = str(data.get("figure") or "").strip()
    if not figure_text:
        raise GeobenchError("课程里没有 figure")
    try:
        figure = parse_dsl(figure_text)
    except (DSLParseError, GeobenchError) as exc:
        raise GeobenchError(f"figure 解析失败：{exc}") from exc
    if len(figure.nodes) > 80:
        raise GeobenchError(
            f"图形太大了（{len(figure.nodes)} 个对象）；"
            "请只画题目相关的对象和必要的辅助线。"
        )
    if progress is not None:
        progress("正在求值、检查图形…")
    problems = check_figure(figure, registry)
    if problems:
        raise GeobenchError(
            "figure 里有对象没有值："
            + "；".join(problem.to_text() for problem in problems)
        )
    _intersection_lint(figure)
    node_kinds = _node_kinds(figure)
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise GeobenchError("课程里没有 steps")
    if not _MIN_STEPS <= len(raw_steps) <= _MAX_STEPS:
        raise GeobenchError(
            f"steps 要有 {_MIN_STEPS}–{_MAX_STEPS} 步，现在是 {len(raw_steps)} 步"
        )
    steps: list[TutorStep] = []
    judges = JudgeRegistry()
    for index, raw_step in enumerate(raw_steps, 1):
        if not isinstance(raw_step, dict):
            raise GeobenchError(f"第 {index} 步不是一个对象")
        say = str(raw_step.get("say") or "").strip()
        if not say:
            raise GeobenchError(f"第 {index} 步没有 say")
        claim = _claim(raw_step.get("claim"), node_kinds)
        if claim is not None and progress is not None:
            progress(f"正在核对第 {index} 步的几何事实…")
        if claim is not None and claim.scope != IDENTITY:
            # A lesson is a proof, not a snapshot: choosing `instance`
            # would let a figure that merely *looks* right dodge the
            # counterexample.  Encode the givens instead.
            raise GeobenchError(
                f"第 {index} 步的 claim 应该用 scope=identity（证明），"
                f"不是 {claim.scope}；请把题目条件画成构造。"
            )
        if claim is not None:
            # The model does not get to hand the student a false step.
            # `supported` is accepted -- every sample passed and the
            # field could not finish the identity proof -- but a
            # counterexample or an undefined value goes back as feedback.
            verdict = judge_relation(
                figure,
                claim.kind,
                list(claim.args),
                judges,
                scope=claim.scope,
            )
            if verdict.verdict in (REFUTED, UNDECIDED):
                raise GeobenchError(
                    f"第 {index} 步的 claim {claim.kind}"
                    f"({', '.join(claim.args)}) 内核判为{verdict.verdict}。"
                    + _claim_hint(claim, verdict)
                )
        steps.append(
            TutorStep(
                say=say,
                reveal=_names(raw_step.get("reveal"), node_kinds, f"第 {index} 步的 reveal"),
                highlight=_names(
                    raw_step.get("highlight"), node_kinds, f"第 {index} 步的 highlight"
                ),
                claim=claim,
                ask=str(raw_step.get("ask") or "").strip(),
            )
        )
    if not any(step.claim is not None for step in steps):
        raise GeobenchError("steps 里没有一条可核对的事实；请给关键步骤加上 claim")
    return Lesson(
        title=title,
        problem=problem.strip(),
        figure=figure_text,
        goal=goal,
        steps=tuple(steps),
    )


def build_lesson(
    provider: Provider,
    problem: str,
    registry: OperatorRegistry,
    retries: int = 2,
    progress: Callable[[str], None] | None = None,
) -> Lesson:
    """Ask for a figure and a lesson, and refuse a lesson that cannot run.

    The retry is the same loop the figure channel uses: the parser and
    the kernel say what is wrong, and the model gets one more try with
    that complaint.  A model that cannot produce a usable figure after
    the retries has not produced a lesson -- saying so is better than
    showing a broken canvas.
    """
    if not problem.strip():
        raise GeobenchError("题目是空的")
    system = _prompt(_LESSON_PROMPT, registry)
    user = (
        "题目：\n"
        f"{problem.strip()}\n\n"
        "请先画出题目给出的图形（辅助对象写好并隐藏），再给出 3–8 步的讲解提纲。"
    )
    client = _with_budget(provider, 3000)
    feedback = ""
    for _attempt in range(retries + 1):
        if progress is not None:
            progress(f"正在问模型（第 {_attempt + 1} 次）…")
        message = user if not feedback else f"{user}\n\n{feedback}"
        text = client.complete(system, message)
        if progress is not None:
            progress("模型已返回，正在解析图形…")
        try:
            return _lesson_from(json_object(text), problem, registry, progress)
        except GeobenchError as exc:
            feedback = (
                f"上一次输出不能用：{exc}\n"
                "请修正图形或步骤，只输出完整的 JSON。"
            )
            if progress is not None and _attempt < retries:
                progress("这次没有通过，正在让模型修正…")
    raise GeobenchError(f"模型没有给出可用的课程：{feedback}")


def _reply_from(
    data: object, node_kinds: dict[str, str], registry: OperatorRegistry
) -> TutorReply:
    """Validate one answer before the app applies any of its actions."""
    if not isinstance(data, dict):
        raise GeobenchError("模型没有返回一个 JSON 对象")
    say = str(data.get("say") or "").strip()
    if not say:
        raise GeobenchError("回复里没有 say")
    provisional = dict(node_kinds)
    raw_constructs = data.get("construct")
    constructs: list[ConstructOp] = []
    if raw_constructs is not None:
        if not isinstance(raw_constructs, list):
            raise GeobenchError("construct 必须是列表")
        for raw in raw_constructs:
            if not isinstance(raw, dict):
                raise GeobenchError("construct 里有一项不是对象")
            op = str(raw.get("op") or "").strip()
            node_id = str(raw.get("id") or "").strip()
            args = raw.get("args") or []
            if not isinstance(args, list) or not op or not node_id:
                raise GeobenchError("construct 需要 op、args 和 id")
            try:
                spec = registry.lookup(op)
            except RegistryError as exc:
                raise GeobenchError(f"construct 里的命令 {op!r} 不存在") from exc
            if not registry.has_implementation(op):
                raise GeobenchError(f"construct 里的命令 {op!r} 还没有实现")
            if node_id in provisional:
                raise GeobenchError(f"construct 的 id {node_id!r} 和现有对象重名")
            constructs.append(
                ConstructOp(
                    op=op,
                    args=tuple(str(arg) for arg in args),
                    id=node_id,
                )
            )
            provisional[node_id] = spec.returns
    return TutorReply(
        say=say,
        highlight=_names(data.get("highlight"), node_kinds, "highlight"),
        reveal=_names(data.get("reveal"), node_kinds, "reveal"),
        construct=tuple(constructs),
        claim=_claim(data.get("claim"), provisional),
        ask=str(data.get("ask") or "").strip(),
    )


def _lesson_outline(lesson: Lesson) -> str:
    lines = [f"题目：{lesson.problem}", f"目标：{lesson.goal}"]
    for index, step in enumerate(lesson.steps, 1):
        lines.append(f"{index}. {step.say}")
    return "\n".join(lines)


def answer_question(
    provider: Provider,
    lesson: Lesson,
    step_index: int,
    question: str,
    figure_dsl: str,
    history: list[tuple[str, str]],
    registry: OperatorRegistry,
) -> TutorReply:
    """Answer a student's question about the current step."""
    if not question.strip():
        raise GeobenchError("问题是空的")
    try:
        figure = parse_dsl(figure_dsl)
    except (DSLParseError, GeobenchError) as exc:
        raise GeobenchError(f"当前图形读不了：{exc}") from exc
    node_kinds = _node_kinds(figure)
    current = (
        lesson.steps[step_index]
        if 0 <= step_index < len(lesson.steps)
        else None
    )
    conversation = "\n".join(f"{role}：{text}" for role, text in history[-8:])
    system = _prompt(_REPLY_PROMPT, registry)
    user = (
        f"{_lesson_outline(lesson)}\n\n"
        f"当前步骤：第 {step_index + 1} 步\n"
        + (f"{current.say}\n" if current is not None else "还没有开始。\n")
        + "\n当前图形：\n```\n"
        f"{figure_dsl.strip()}\n```\n\n"
        + (f"最近对话：\n{conversation}\n\n" if conversation else "")
        + f"学生这次说：\n{question.strip()}\n"
    )
    client = _with_budget(provider, 1000)
    return _reply_from(
        json_object(client.complete(system, user)), node_kinds, registry
    )
