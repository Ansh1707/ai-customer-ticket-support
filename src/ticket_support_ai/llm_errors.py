"""Shared model integration errors."""


class LLMError(RuntimeError):
    """Base class for safe, user-facing model integration failures."""


class QuestionValidationError(LLMError):
    """Raised before a request when the natural-language question is invalid."""


class OllamaUnavailableError(LLMError):
    """Raised when the local Ollama service cannot be reached."""


class OllamaTimeoutError(LLMError):
    """Raised when local inference exceeds the configured timeout."""


class OllamaModelNotFoundError(LLMError):
    """Raised when Ollama is running but the configured model is unavailable."""


class OllamaResponseError(LLMError):
    """Raised for an unexpected Ollama HTTP or response-shape failure."""


class StructuredOutputError(LLMError):
    """Raised when all schema-correction attempts have failed."""
