"""Where the model service comes from.

The practice every agent tool shares is a **precedence**, not a single
answer. Claude Code, Cursor, Cline, Continue, Copilot CLI, OpenCode
and Gemini CLI all do the same three things in the same order:

1. **an environment variable** -- the key never lands on disk, and the
   user has usually already exported one;
2. **the operating system's credential store** -- safe, but not every
   machine has one, and not every tool can reach it;
3. **the application's own settings** -- the last resort, and the one
   that needs a warning.

The precedence here is the one Claude Code documents: **the environment
wins**. A user who already exported a key is not asked again, and on
a machine where ``DEEPSEEK_API_KEY`` is already set the studio works
with no configuration at all.

The key file is the third choice on purpose: it is a file the user
points at (``.env``-style), so the key lives where the user expects
it, and the settings only remember *where*. The key and the settings
are kept apart so that the settings can be copied and shared without
the key going with them.

Nothing here is in the kernel: the kernel has no model in it
(decision D4). This is the service layer, and the studio can be turned
off without it noticing.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from geobench.ai import OpenAICompatibleProvider

__all__ = [
    "PROVIDERS",
    "AISettings",
    "ProviderPreset",
    "Resolution",
    "config_path",
    "environment_services",
    "key_file_path",
    "key_from_environment",
    "read_key_file",
    "read_settings",
    "requires_key",
    "resolve_provider",
    "write_key_file",
    "write_settings",
]


@dataclass(frozen=True)
class ProviderPreset:
    """One service: where it lives, what it is called, what it calls itself."""

    label: str
    base_url: str
    model: str
    env_names: tuple[str, ...] = ()
    """The environment variables this service is usually reached by."""

    note: str = ""
    """Something the user should know before choosing this one."""


#: The services that speak the OpenAI chat API. Anthropic's own API is
#: deliberately not here: it is not OpenAI-compatible, so it needs a
#: different client, and pretending otherwise would be a trap.
PROVIDERS: dict[str, ProviderPreset] = {
    "deepseek": ProviderPreset(
        "DeepSeek",
        "https://api.deepseek.com/v1",
        "deepseek-chat",
        ("DEEPSEEK_API_KEY",),
    ),
    "openai": ProviderPreset(
        "OpenAI",
        "https://api.openai.com/v1",
        "gpt-4o-mini",
        ("OPENAI_API_KEY",),
    ),
    "qwen": ProviderPreset(
        "通义千问(阿里云百炼)",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus",
        ("DASHSCOPE_API_KEY",),
    ),
    "moonshot": ProviderPreset(
        "Moonshot(Kimi)",
        "https://api.moonshot.cn/v1",
        "kimi-k3",
        ("MOONSHOT_API_KEY",),
        note="国内平台用 .cn，境外平台用 .ai",
    ),
    "minimax": ProviderPreset(
        "MiniMax",
        "https://api.minimax.io/v1",
        "MiniMax-M3",
        ("MINIMAX_API_KEY",),
        note="国内平台用 api.minimaxi.com",
    ),
    "siliconflow": ProviderPreset(
        "SiliconFlow(硅基流动)",
        "https://api.siliconflow.cn/v1",
        "Qwen/Qwen2.5-72B-Instruct",
        ("SILICONFLOW_API_KEY",),
    ),
    "openrouter": ProviderPreset(
        "OpenRouter",
        "https://openrouter.ai/api/v1",
        "openai/gpt-4o-mini",
        ("OPENROUTER_API_KEY",),
    ),
    "groq": ProviderPreset(
        "Groq",
        "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile",
        ("GROQ_API_KEY",),
    ),
    "ollama": ProviderPreset(
        "Ollama(本机)",
        "http://localhost:11434/v1",
        "llama3",
        (),
        note="本机跑着模型就不需要钥匙",
    ),
    "custom": ProviderPreset("自定义", "", "", ()),
}

#: The environment variable that overrides everything, whatever the
#: service is called. It is the one variable that is *about* this
#: application, so it outranks the service's own variables.
OVERRIDE_ENV = "GEOBENCH_AI_API_KEY"

#: The environment variables that override the address and the model.
OVERRIDE_BASE_URL = "GEOBENCH_AI_BASE_URL"
OVERRIDE_MODEL = "GEOBENCH_AI_MODEL"


def config_path() -> Path:
    """Where the studio keeps its own settings.

    The platform's own place for it: ``%APPDATA%`` on Windows,
    ``~/.config`` elsewhere. ``GEOBENCH_CONFIG_DIR`` overrides both --
    which is what a portable install wants, and what the tests want.
    """
    override = os.environ.get("GEOBENCH_CONFIG_DIR", "").strip()
    if override:
        return Path(override) / "settings.json"
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return root / "geobench" / "settings.json"


def key_file_path() -> Path:
    """The default place for the key, when the user lets the app keep it.

    A separate file from the settings, so that the settings can be
    copied and shared without the key going with them.
    """
    return config_path().parent / "api_key"


@dataclass
class AISettings:
    """What the studio knows about the model service."""

    provider: str = ""
    base_url: str = ""
    model: str = ""
    key_file: str = ""
    """Where the key lives. Empty means: the default place."""

    prefer_stored_key: bool = False
    """Whether the key the app holds wins over the environment.

    Off by default, because the environment wins in every tool that
    has a choice -- but a user who typed a key into this application
    means that key, and should be able to say so.
    """

    def preset(self) -> ProviderPreset | None:
        return PROVIDERS.get(self.provider)

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "key_file": self.key_file,
            "prefer_stored_key": self.prefer_stored_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AISettings:
        return cls(
            provider=str(data.get("provider", "")),
            base_url=str(data.get("base_url", "")),
            model=str(data.get("model", "")),
            key_file=str(data.get("key_file", "")),
            prefer_stored_key=bool(data.get("prefer_stored_key", False)),
        )


def read_settings() -> AISettings:
    """The studio's own settings, or the defaults if there are none."""
    path = config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AISettings()
    if not isinstance(data, dict):
        return AISettings()
    return AISettings.from_dict(data)


def write_settings(settings: AISettings) -> Path:
    """Save the studio's own settings."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def read_key_file(path: str | Path) -> str:
    """The key in a key file, if there is one.

    The file is ``.env``-style: a line ``API_KEY=...``, or just the
    key on its own line. A key in the file may also be written as
    ``${SOME_ENV_VAR}``, which is what Continue does -- the file says
    where the key is without containing it.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            name, _, value = line.partition("=")
            if name.strip().upper() in {"API_KEY", "KEY", "GEOBENCH_AI_API_KEY"}:
                line = value.strip()
            else:
                continue
        return _expand(line.strip().strip('"').strip("'"))
    return ""


def _expand(value: str) -> str:
    """Replace a ``${NAME}`` with the environment variable it names."""
    if value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def write_key_file(path: str | Path, key: str) -> Path:
    """Put the key in the key file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"API_KEY={key}\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        # A key file is a secret: on the systems that have such a thing,
        # only the user should be able to read it.
        target.chmod(0o600)
    return target


def requires_key(base_url: str) -> bool:
    """Whether a service at this address needs a key at all.

    A model running on this machine does not, and pretending that it
    does would send the user off to fetch a key that does not exist.
    """
    host = base_url.split("//")[-1].split("/")[0].split(":")[0].strip().lower()
    return host not in {"", "localhost", "127.0.0.1", "0.0.0.0", "::1"}


def environment_services() -> list[tuple[str, str]]:
    """The services whose key the environment already holds.

    ``(provider id, environment variable name)``, in the order the
    presets are written. This is what the studio offers when the user
    asks it to look for a key that is already there.
    """
    found: list[tuple[str, str]] = []
    for provider_id, preset in PROVIDERS.items():
        for name in preset.env_names:
            if os.environ.get(name, "").strip():
                found.append((provider_id, name))
                break
    return found


def key_from_environment(preset: ProviderPreset | None) -> tuple[str, str]:
    """The key the environment already holds for this service.

    The override variable wins, then the service's own variables. The
    name comes back with it, so that the studio can say *which*
    variable it found -- a user who does not know what an environment
    variable is should not have to guess.
    """
    override = os.environ.get(OVERRIDE_ENV, "").strip()
    if override:
        return override, OVERRIDE_ENV
    if preset is not None:
        for name in preset.env_names:
            value = os.environ.get(name, "").strip()
            if value:
                return value, name
    return "", ""


@dataclass(frozen=True)
class Resolution:
    """What the studio resolved the model service to.

    ``provider`` is ``None`` when there is nothing to talk to, and
    ``reason`` then says what is missing -- because "it does not work"
    is not an answer.
    """

    provider: OpenAICompatibleProvider | None = None
    source_kind: str = ""
    """``"env"``, ``"file"``, or ""."""

    source_name: str = ""
    """The environment variable's name, or the key file's path."""

    reason: str = ""
    """``"missing-key"``, ``"missing-url"``, ``"missing-model"``."""

    @property
    def ok(self) -> bool:
        return self.provider is not None


def resolve_provider(settings: AISettings | None = None) -> Resolution:
    """The provider to use, and where its key came from.

    The order is the one every agent tool uses: **the environment
    first**, then the key file. A user who already exported a key is
    not asked again.
    """
    settings = settings if settings is not None else read_settings()
    preset = settings.preset()
    auto_service = ""

    if preset is None and not settings.base_url:
        # Nothing is configured. If the environment already holds a key
        # for a service we know, that service is the one: the point of
        # reading the environment first is that a user who has already
        # exported a key should not have to configure anything.
        found = environment_services()
        if found:
            provider_id, name = found[0]
            preset = PROVIDERS.get(provider_id)
            auto_service = name

    base_url = (
        os.environ.get(OVERRIDE_BASE_URL, "").strip()
        or settings.base_url
        or (preset.base_url if preset else "")
    )
    model = (
        os.environ.get(OVERRIDE_MODEL, "").strip()
        or settings.model
        or (preset.model if preset else "")
    )

    key, env_name = key_from_environment(preset)
    source_kind = "env" if env_name else ""
    source_name = env_name or auto_service

    key_file = settings.key_file or str(key_file_path())
    if not key or settings.prefer_stored_key:
        stored = read_key_file(key_file)
        if stored:
            key = stored
            source_kind = "file"
            source_name = key_file

    if not base_url:
        return Resolution(reason="missing-url")
    if not model:
        return Resolution(reason="missing-model")
    if not key and requires_key(base_url):
        return Resolution(reason="missing-key")

    provider = OpenAICompatibleProvider(model=model, base_url=base_url, api_key=key)
    provider.name = preset.label if preset else "自定义"
    return Resolution(provider=provider, source_kind=source_kind, source_name=source_name)
