"""Tests for environment-backed local Ollama settings."""

from __future__ import annotations

import pytest

from ticket_support_ai.config import OllamaSettings


def test_ollama_settings_defaults_target_local_qwen() -> None:
    settings = OllamaSettings()

    assert settings.base_url == "http://127.0.0.1:11434"
    assert settings.model == "qwen2.5:3b"
    assert settings.context_tokens == 4096
    assert settings.response_tokens == 512
    assert settings.request_timeout_seconds == 60
    assert settings.corrective_retries == 1


def test_ollama_settings_load_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:9999/")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen-test:3b")
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT", "12.5")
    monkeypatch.setenv("OLLAMA_CONTEXT_TOKENS", "8192")

    settings = OllamaSettings.from_environment()

    assert settings.base_url == "http://localhost:9999"
    assert settings.model == "qwen-test:3b"
    assert settings.request_timeout_seconds == 12.5
    assert settings.context_tokens == 8192


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_url": "localhost:11434"},
        {"model": "  "},
        {"request_timeout_seconds": 0},
        {"context_tokens": 512},
        {"response_tokens": 100},
        {"corrective_retries": 2},
        {"max_question_chars": 0},
    ],
)
def test_ollama_settings_reject_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        OllamaSettings(**kwargs)


def test_ollama_settings_reject_invalid_numeric_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_CONTEXT_TOKENS", "many")

    with pytest.raises(ValueError, match="must be an integer"):
        OllamaSettings.from_environment()
