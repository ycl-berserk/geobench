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
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from geobench.commands import COMMANDS
from geobench.dsl import parse_dsl
from geobench.errors import GeobenchError
from geobench.model import Figure
from geobench.registry import OperatorRegistry

__all__ = [
    "PROMPT_PATH",
    "OpenAICompatibleProvider",
    "Proposal",
    "Provider",
    "build_prompt",
    "propose",
]

#: The prompt template. The command list is filled in from the command
#: table, so the model can never be told about a command that does not
#: exist, or miss one that does.
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "nl-to-dsl.md"


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
    """

    text: str
    figure: Figure | None = None
    error: str | None = None
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return self.figure is not None


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
    """
    template = PROMPT_PATH.read_text(encoding="utf-8")
    system = template.replace("{commands}", command_list(registry))
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
    retries: int = 1,
) -> Proposal:
    """Ask the model for a figure, and let the parser judge it.

    The parser's complaint goes back to the model, once: a model that
    is told "line 3: 点 A 的坐标应该是两个数" usually gets it right the
    second time. If it does not, the proposal is refused -- and the
    refusal is the honest answer.
    """
    system, user = build_prompt(request, current, registry)
    last_error: str | None = None
    for attempt in range(1, max(1, retries + 1) + 1):
        message = user
        if last_error is not None:
            message = (
                f"{user}\n\n"
                "上一次你写的作图代码解析失败了：\n"
                f"{last_error}\n"
                "请修正后重新给出完整的作图代码。"
            )
        text = _clean(provider.complete(system, message))
        try:
            figure = parse_dsl(text)
        except GeobenchError as exc:
            last_error = str(exc)
            continue
        except Exception as exc:  # pragma: no cover - the parser's own errors
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        return Proposal(text=text, figure=figure, attempts=attempt)
    return Proposal(text=text, error=last_error or "the model said nothing usable", attempts=attempt)
