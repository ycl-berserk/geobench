"""The model writes the DSL; the parser decides whether it is a figure.

This is the whole of the AI design, and it is one sentence: **the
model translates, the parser rejects** (``docs/ai-workflow.md`` §10).
The reliability of the text-to-figure channel comes from that division
of labour, not from the model being cleverer.

So the model never touches the kernel. It writes text. The parser
either accepts that text as a figure or refuses it, with a line and a
reason. The figure that comes out is checked by the same judges as
every other figure, and a wrong proposal is a rejected proposal, not a
wrong picture.

Nothing here is in the kernel either: the kernel has no model in it
(decision D4). This module is the service layer, and it can be turned
off without the studio noticing.

**Where the key comes from is not decided here.** This module is the
transport: it speaks the OpenAI chat API, whoever that is. The policy
-- environment first, then the key file, then the app's own settings --
lives in ``geobench.ai_settings``, so that there is exactly one place
that knows the answer.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from geobench.commands import COMMANDS
from geobench.dsl import parse_dsl
from geobench.errors import GeobenchError
from geobench.evaluate import evaluate_figure, undefined_nodes
from geobench.judges import INSTANCE, REFUTED, UNDECIDED, JudgeRegistry, judge_relation
from geobench.model import Figure
from geobench.registry import OperatorRegistry

__all__ = [
    "PROMPT_PATH",
    "OpenAICompatibleProvider",
    "Problem",
    "Proposal",
    "Provider",
    "build_prompt",
    "check_figure",
    "propose",
]

#: The prompt template. The command list is filled in from the command
#: table, so the model can never be told about a command that does not
#: exist, or miss one that does.
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "nl-to-dsl.md"

#: The conventions a competition figure follows.  The model is told the
#: rules; without them it draws a figure that is right but does not look
#: like the one in the paper.
STANDARDS_PATH = Path(__file__).resolve().parents[2] / "prompts" / "figure-standards.md"

#: Worked examples.  A rule that is demonstrated is obeyed; a rule that
#: is only stated is forgotten -- and the difference between the two is
#: the whole reliability of this channel.
EXAMPLES_PATH = Path(__file__).resolve().parents[2] / "prompts" / "figure-examples.md"


class Provider(Protocol):
    """Something that can answer a prompt."""

    name: str

    def complete(self, system: str, user: str) -> str:
        """Answer the prompt, in text."""


@dataclass
class OpenAICompatibleProvider:
    """A provider that speaks the OpenAI chat API.

    Many services speak it -- the hosted ones and the local ones alike
    -- so one client reaches them all. The key comes from the
    environment: a key is a secret, and a secret does not belong in a
    file the user might send to somebody.
    """

    model: str
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    timeout: float = 60
    name: str = "openai-compatible"

    def complete(self, system: str, user: str) -> str:
        """Ask the model, and return what it said."""
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - needs a service
            raise GeobenchError(f"the model service refused: {exc}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover - needs a service
            raise GeobenchError(f"the model service is not reachable: {exc}") from exc
        try:
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:  # pragma: no cover
            raise GeobenchError("the model service said something unexpected") from exc


@dataclass
class Proposal:
    """What the model proposed, and what the parser made of it.

    ``figure`` is set only when the text parsed. ``error`` is the
    parser's own complaint -- the line and the reason -- and it is the
    answer that matters: it says exactly what the model got wrong, and
    it can be sent back.

    ``problems`` is the kernel's own verdict on the figure: an object
    that cannot exist, or a claim the drawn figure does not satisfy.
    Those are not parser errors -- the code is perfectly good -- but
    they are exactly what a teacher would bounce the picture for, so
    they are said out loud.
    """

    text: str
    figure: Figure | None = None
    error: str | None = None
    attempts: int = 1
    problems: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.figure is not None

    @property
    def clean(self) -> bool:
        """The figure is not just parseable, but sound."""
        return self.ok and not self.problems

    @property
    def refused(self) -> bool:
        """The model said the request cannot be done.

        A request like "draw the tangent from a point inside the circle"
        has no answer, and the honest reply is to say so.  The model
        says it in a comment, so the figure is empty and the words are
        in the text.
        """
        return (
            self.figure is not None
            and not self.figure.nodes
            and "#" in self.text
        )


@dataclass(frozen=True)
class Problem:
    """Something wrong with the figure the model proposed.

    The kernel is the judge of a figure, not only of a relation.  Two
    things are wrong with a figure that the parser cannot see: an
    object that **cannot exist** (the intersection of two lines that
    are always parallel), and a **claim the drawn figure does not
    satisfy** (the tangent from a point inside a circle).  Both are
    things the model can fix, so both are said out loud and sent back.
    """

    kind: str
    """``"no-value"``, ``"refuted"``, ``"undecided"`` or ``"broken"``."""

    subject: str
    """The object or the relation at fault."""

    reason: str = ""
    """The kernel's own words about it."""

    def to_text(self) -> str:
        """The problem, in the language of the classroom."""
        if self.kind == "no-value":
            return f"对象 {self.subject} 没有值（{self.reason}）"
        if self.kind == "refuted":
            return f"断言 {self.subject} 在这张图上不成立"
        if self.kind == "undecided":
            return f"断言 {self.subject} 无法判定（{self.reason}）"
        return f"这张图画不出来：{self.reason}"


def check_figure(figure: Figure, registry: OperatorRegistry) -> list[Problem]:
    """What is wrong with this figure, if anything.

    The figure is evaluated first -- the judge needs the exact path --
    and then two things are looked at:

    - the objects that have **no value** (a degenerate construction);
    - the claims the figure makes, judged **in the drawn
      configuration**, because that is the question "is this picture
      consistent with what it claims" -- and it is answered in
      milliseconds, while the theorem-level question can take a minute.
    """
    problems: list[Problem] = []
    try:
        evaluated = evaluate_figure(figure, registry)
    except GeobenchError as exc:
        return [Problem(kind="broken", subject="整张图", reason=str(exc))]
    for node_id, reason in undefined_nodes(evaluated):
        problems.append(Problem(kind="no-value", subject=node_id, reason=reason))
    if not evaluated.relations:
        return problems
    judges = JudgeRegistry()
    for relation in evaluated.relations:
        subject = f"{relation.kind}({', '.join(relation.args)})"
        verdict = judge_relation(
            evaluated, relation.kind, list(relation.args), judges, scope=INSTANCE
        )
        if verdict.verdict == REFUTED:
            problems.append(Problem(kind="refuted", subject=subject))
        elif verdict.verdict == UNDECIDED:
            problems.append(
                Problem(kind="undecided", subject=subject, reason=verdict.evidence)
            )
    return problems


def command_list(registry: OperatorRegistry | None = None) -> str:
    """The commands the model may use, one per line.

    It is written from the command table and the operator registry, so
    a command that does not exist cannot appear here, and one that
    exists cannot be missing.
    """
    lines: list[str] = []
    for command in COMMANDS:
        if command.kind == "判定" or not command.implemented:
            continue
        shape = ""
        if registry is not None:
            try:
                spec = registry.lookup(command.id)
            except GeobenchError:
                spec = None
            if spec is not None:
                shape = ", ".join(arg.type for arg in spec.args)
        lines.append(f"- {command.name_zh}({shape}) —— {command.summary}")
    return "\n".join(lines)


def build_prompt(request: str, current: str = "", registry: OperatorRegistry | None = None) -> tuple[str, str]:
    """The system prompt and the user's message.

    The current figure is given as context, so the model can use the
    points that are already there instead of inventing new ones.

    The prompt is in three layers, and each layer earns its place:

    - the **rules** (the template), short and pointed;
    - the **standards** -- the conventions of a competition figure;
    - the **examples** -- worked figures, which are obeyed far more
      reliably than rules are;
    - and the **command list**, which is generated from the command table
      so that it cannot drift away from the code.
    """
    template = PROMPT_PATH.read_text(encoding="utf-8")
    system = (
        template.replace("{commands}", command_list(registry))
        .replace("{standards}", STANDARDS_PATH.read_text(encoding="utf-8"))
        .replace("{examples}", EXAMPLES_PATH.read_text(encoding="utf-8"))
    )
    if current.strip():
        user = (
            "当前这张图是这样的（这是背景，不要改动它）：\n"
            "```\n"
            f"{current.strip()}\n"
            "```\n\n"
            "请完成这个任务：\n"
            f"{request.strip()}\n"
        )
    else:
        user = f"请完成这个任务：\n{request.strip()}\n"
    return system, user


def _clean(text: str) -> str:
    """The DSL, without the code fence the model likes to add."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def propose(
    provider: Provider,
    request: str,
    current: str = "",
    registry: OperatorRegistry | None = None,
    retries: int = 2,
) -> Proposal:
    """Ask the model for a figure, and let the kernel judge it.

    There are two kinds of "no", and both go back to the model:

    - the **parser** refuses the text -- it says which line and what is
      wrong with it;
    - the **kernel** judges the figure -- an object that cannot exist,
      or a claim the drawn figure does not satisfy.

    The second one is the interesting half.  A model that is told "your
    figure has an object with no value: the two lines are parallel"
    fixes it; a model that is only told "the parser said no" fixes the
    syntax and repeats the same mistake.
    """
    system, user = build_prompt(request, current, registry)
    feedback: str | None = None
    text = ""
    attempt = 0
    figure: Figure | None = None
    problems: list[Problem] = []
    for attempt in range(1, max(1, retries + 1) + 1):
        message = user
        if feedback is not None:
            message = (
                f"{user}\n\n"
                f"{feedback}\n"
                "请修正后重新给出完整的作图代码（还是只输出代码）。"
            )
        text = _clean(provider.complete(system, message))
        try:
            figure = parse_dsl(text)
        except GeobenchError as exc:
            feedback = f"上一次你写的作图代码解析失败了：\n{exc}"
            continue
        except Exception as exc:  # pragma: no cover - the parser's own errors
            feedback = f"上一次你写的作图代码解析失败了：\n{type(exc).__name__}: {exc}"
            continue
        problems = check_figure(figure, registry) if registry is not None else []
        if not problems or attempt == max(1, retries + 1):
            return Proposal(
                text=text, figure=figure, attempts=attempt, problems=problems
            )
        feedback = (
            "上一次你写的作图代码解析器接受了，但内核查出图有问题：\n"
            + "\n".join(f"- {problem.to_text()}" for problem in problems)
            + "\n请改到没有问题为止。"
        )
    return Proposal(
        text=text,
        error=feedback if figure is None else None,
        attempts=attempt,
        problems=problems,
    )
