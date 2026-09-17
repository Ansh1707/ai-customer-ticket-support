"""Application configuration and environment settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"


@dataclass(frozen=True, slots=True)
class OllamaSettings:
    """Validated settings for deterministic local-model interpretation."""

    base_url: str = DEFAULT_OLLAMA_BASE_URL
    model: str = DEFAULT_OLLAMA_MODEL
    connect_timeout_seconds: float = 3.0
    request_timeout_seconds: float = 60.0
    context_tokens: int = 4096
    response_tokens: int = 512
    corrective_retries: int = 1
    max_question_chars: int = 2000

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OLLAMA_BASE_URL must be an absolute HTTP(S) URL.")
        if not self.model.strip():
            raise ValueError("OLLAMA_MODEL must not be blank.")
        if self.connect_timeout_seconds <= 0 or self.request_timeout_seconds <= 0:
            raise ValueError("Ollama timeouts must be greater than zero.")
        if self.context_tokens < 1024:
            raise ValueError("Ollama context must be at least 1024 tokens.")
        if self.response_tokens < 256:
            raise ValueError("Ollama response allowance must be at least 256 tokens.")
        if self.corrective_retries not in {0, 1}:
            raise ValueError("Ollama corrective retries must be zero or one.")
        if self.max_question_chars < 1:
            raise ValueError("Maximum question length must be positive.")

    @classmethod
    def from_environment(cls) -> OllamaSettings:
        """Load optional environment overrides without requiring a secrets file."""

        return cls(
            base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/"),
            model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            connect_timeout_seconds=_float_env("OLLAMA_CONNECT_TIMEOUT", 3.0),
            request_timeout_seconds=_float_env("OLLAMA_REQUEST_TIMEOUT", 60.0),
            context_tokens=_int_env("OLLAMA_CONTEXT_TOKENS", 4096),
            response_tokens=_int_env("OLLAMA_RESPONSE_TOKENS", 512),
            corrective_retries=_int_env("OLLAMA_CORRECTIVE_RETRIES", 1),
            max_question_chars=_int_env("MAX_QUESTION_CHARS", 2000),
        )


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric.") from exc


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
