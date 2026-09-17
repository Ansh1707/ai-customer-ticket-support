"""Request-scoped, privacy-conscious diagnostics for the local prototype."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime

LOGGER = logging.getLogger("ticket_support_ai.diagnostics")
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.propagate = False


@dataclass(slots=True)
class RequestDiagnostics:
    """Mutable counters retained only for the lifetime of one HTTP request."""

    request_id: str
    outcome: str | None = None
    error_code: str | None = None
    model_latency_ms: float = 0.0
    retries: int = 0
    validation_errors: int = 0
    validation_error_kinds: list[str] = field(default_factory=list)


_CURRENT: ContextVar[RequestDiagnostics | None] = ContextVar(
    "ticket_support_request_diagnostics",
    default=None,
)


def begin_request(request_id: str) -> Token[RequestDiagnostics | None]:
    """Create request-local state and return the token needed to clear it."""

    return _CURRENT.set(RequestDiagnostics(request_id=request_id))


def end_request(token: Token[RequestDiagnostics | None]) -> None:
    """Restore the previous diagnostic context."""

    _CURRENT.reset(token)


def current_diagnostics() -> RequestDiagnostics | None:
    """Return current request state, or ``None`` outside an HTTP request."""

    return _CURRENT.get()


def record_model_latency(elapsed_ms: float) -> None:
    state = _CURRENT.get()
    if state is not None:
        state.model_latency_ms += max(0.0, elapsed_ms)


def record_retry() -> None:
    state = _CURRENT.get()
    if state is not None:
        state.retries += 1


def record_validation_error(kind: str) -> None:
    """Record a bounded category without retaining invalid input or model output."""

    state = _CURRENT.get()
    if state is None:
        return
    state.validation_errors += 1
    if kind not in state.validation_error_kinds:
        state.validation_error_kinds.append(kind[:64])


def record_outcome(outcome: str, *, error_code: str | None = None) -> None:
    state = _CURRENT.get()
    if state is not None:
        state.outcome = outcome
        state.error_code = error_code


def log_request_completion(
    *,
    method: str,
    path: str,
    status_code: int,
    total_latency_ms: float,
) -> None:
    """Emit one concise JSON record containing no request or dataset content."""

    state = _CURRENT.get()
    if state is None:
        return
    payload: dict[str, object] = {
        "event": "request_complete",
        "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "request_id": state.request_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "outcome": state.outcome or ("ok" if status_code < 400 else "error"),
        "model_latency_ms": round(state.model_latency_ms, 3),
        "total_latency_ms": round(max(0.0, total_latency_ms), 3),
        "retries": state.retries,
        "validation_errors": state.validation_errors,
        "validation_error_kinds": state.validation_error_kinds,
    }
    if state.error_code is not None:
        payload["error_code"] = state.error_code
    LOGGER.info(json.dumps(payload, separators=(",", ":"), sort_keys=True))
