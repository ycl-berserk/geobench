"""Where the key comes from -- the question every agent tool has to answer.

The studio does not decide that the environment is the only way. It
does what the tools do: **a precedence**, with the environment first, a
key file second, and what the user typed into the application last.

These tests pin that precedence down. They are the reason the dialog
can say "密钥来自环境变量 DEEPSEEK_API_KEY" and mean it.

Nothing here touches the network, and nothing here touches the real
user's settings: ``GEOBENCH_CONFIG_DIR`` points the studio's own
storage at a temporary directory for the length of each test.
"""

from __future__ import annotations

import os

import pytest

from geobench.ai_settings import (
    PROVIDERS,
    AISettings,
    config_path,
    environment_services,
    key_file_path,
    read_key_file,
    read_settings,
    requires_key,
    resolve_provider,
    write_key_file,
    write_settings,
)

#: The variables the studio reads. A test clears all of them, so that
#: the machine the test runs on -- which may well have a real key
#: exported -- cannot change the answer.
KNOWN_KEY_VARS = (
    "GEOBENCH_AI_API_KEY",
    "GEOBENCH_AI_BASE_URL",
    "GEOBENCH_AI_MODEL",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "SILICONFLOW_API_KEY",
    "DASHSCOPE_API_KEY",
    "MOONSHOT_API_KEY",
    "MINIMAX_API_KEY",
    "GROQ_API_KEY",
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """A clean machine and a clean studio directory for every test."""
    for name in KNOWN_KEY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEOBENCH_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path


# -- the precedence -------------------------------------------------------


def test_the_environment_is_read_first() -> None:
    """A key that is already exported is not asked for again.

    This is the precedence Claude Code documents, and the one every
    other agent tool follows: the environment wins.
    """
    os.environ["DEEPSEEK_API_KEY"] = "from-the-environment"
    resolution = resolve_provider(AISettings(provider="deepseek"))
    assert resolution.ok
    assert resolution.provider is not None
    assert resolution.provider.api_key == "from-the-environment"
    assert resolution.source_kind == "env"
    assert resolution.source_name == "DEEPSEEK_API_KEY"


def test_the_key_file_is_read_when_the_environment_has_nothing() -> None:
    """The second tier: a file the user points at."""
    path = key_file_path()
    write_key_file(path, "from-the-file")
    resolution = resolve_provider(AISettings(provider="deepseek"))
    assert resolution.ok
    assert resolution.provider is not None
    assert resolution.provider.api_key == "from-the-file"
    assert resolution.source_kind == "file"


def test_the_environment_beats_the_key_file() -> None:
    """Both are there; the environment wins, and says so."""
    write_key_file(key_file_path(), "from-the-file")
    os.environ["DEEPSEEK_API_KEY"] = "from-the-environment"
    resolution = resolve_provider(AISettings(provider="deepseek"))
    assert resolution.provider is not None
    assert resolution.provider.api_key == "from-the-environment"


def test_a_user_who_typed_a_key_can_have_it_win() -> None:
    """The checkbox in the dialog: the app's own key beats the environment.

    A user who typed a key into this application means that key. The
    environment is the default, not a law.
    """
    write_key_file(key_file_path(), "from-the-file")
    os.environ["DEEPSEEK_API_KEY"] = "from-the-environment"
    resolution = resolve_provider(
        AISettings(provider="deepseek", prefer_stored_key=True)
    )
    assert resolution.provider is not None
    assert resolution.provider.api_key == "from-the-file"
    assert resolution.source_kind == "file"


def test_the_override_variable_outranks_the_service_variable() -> None:
    """``GEOBENCH_AI_API_KEY`` is about this application, so it wins."""
    os.environ["DEEPSEEK_API_KEY"] = "the-service-key"
    os.environ["GEOBENCH_AI_API_KEY"] = "the-override"
    resolution = resolve_provider(AISettings(provider="deepseek"))
    assert resolution.provider is not None
    assert resolution.provider.api_key == "the-override"
    assert resolution.source_name == "GEOBENCH_AI_API_KEY"


def test_a_machine_that_already_has_a_key_needs_no_configuration() -> None:
    """The whole point of reading the environment first.

    A user who has exported ``DEEPSEEK_API_KEY`` should find the studio
    ready to talk to DeepSeek, without having chosen a service first.
    """
    os.environ["DEEPSEEK_API_KEY"] = "from-the-environment"
    resolution = resolve_provider(AISettings())
    assert resolution.ok
    assert resolution.provider is not None
    assert resolution.provider.name == "DeepSeek"
    assert resolution.provider.base_url == "https://api.deepseek.com/v1"
    assert resolution.source_name == "DEEPSEEK_API_KEY"


# -- what is missing ------------------------------------------------------


def test_nothing_configured_says_what_is_missing() -> None:
    """"It does not work" is not an answer."""
    resolution = resolve_provider(AISettings(provider="custom"))
    assert not resolution.ok
    assert resolution.reason == "missing-url"


def test_a_service_without_a_key_says_the_key_is_missing() -> None:
    resolution = resolve_provider(
        AISettings(provider="custom", base_url="https://api.example.com/v1", model="m")
    )
    assert not resolution.ok
    assert resolution.reason == "missing-key"


def test_a_model_on_this_machine_needs_no_key() -> None:
    """Ollama runs here; asking for a key would be asking for nothing."""
    assert requires_key("http://localhost:11434/v1") is False
    assert requires_key("https://api.deepseek.com/v1") is True
    resolution = resolve_provider(
        AISettings(provider="ollama", base_url="http://localhost:11434/v1", model="llama3")
    )
    assert resolution.ok
    assert resolution.provider is not None
    assert resolution.provider.api_key == ""


# -- the settings and the key file ----------------------------------------


def test_the_settings_are_remembered() -> None:
    write_settings(AISettings(provider="qwen", model="qwen-max"))
    settings = read_settings()
    assert settings.provider == "qwen"
    assert settings.model == "qwen-max"


def test_a_broken_settings_file_is_not_a_reason_to_stop() -> None:
    """The studio starts with defaults rather than refusing to open."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("this is not json", encoding="utf-8")
    assert read_settings().provider == ""


def test_the_key_file_is_kept_apart_from_the_settings() -> None:
    """The settings can be shared; the key cannot."""
    write_settings(AISettings(provider="deepseek"))
    write_key_file(key_file_path(), "secret")
    assert "secret" not in config_path().read_text(encoding="utf-8")


def test_a_key_file_may_point_at_an_environment_variable() -> None:
    """The Continue trick: the file says where the key is, not what it is."""
    os.environ["MY_OWN_KEY"] = "the-real-key"
    path = key_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("API_KEY=${MY_OWN_KEY}\n", encoding="utf-8")
    assert read_key_file(path) == "the-real-key"


def test_a_key_file_may_hold_the_key_itself() -> None:
    path = key_file_path()
    write_key_file(path, "the-real-key")
    assert read_key_file(path) == "the-real-key"


def test_a_key_file_that_is_not_there_is_not_a_reason_to_stop() -> None:
    assert read_key_file(key_file_path() / "nowhere") == ""


# -- the presets ----------------------------------------------------------


def test_every_preset_speaks_the_openai_protocol() -> None:
    """Anthropic's own API is not here: it does not speak this protocol."""
    for provider_id, preset in PROVIDERS.items():
        if provider_id == "custom":
            continue
        assert preset.base_url.startswith("http"), provider_id
        assert preset.model, provider_id


def test_the_environment_is_scanned_for_a_key() -> None:
    """The dialog does not make the user guess which variable to look at."""
    assert environment_services() == []
    os.environ["DEEPSEEK_API_KEY"] = "x"
    found = environment_services()
    assert found == [("deepseek", "DEEPSEEK_API_KEY")]
