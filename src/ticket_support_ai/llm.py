"""Ollama transport and bounded structured interpretation orchestration."""

from __future__ import annotations

import asyncio
import json
from time import perf_counter
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from ticket_support_ai.capabilities import capability_limitation
from ticket_support_ai.config import OllamaSettings
from ticket_support_ai.diagnostics import (
    record_model_latency,
    record_retry,
    record_validation_error,
)
from ticket_support_ai.llm_errors import (
    LLMError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    QuestionValidationError,
    StructuredOutputError,
)
from ticket_support_ai.llm_plans import (
    AnalyticsPlan,
    IntentRoute,
    NumericConditionPlan,
    OllamaModelStatus,
)
from ticket_support_ai.llm_prompts import (
    ANALYTICS_PLAN_PROMPT,
    ROUTER_PROMPT,
    SYSTEM_PROMPT,
)
from ticket_support_ai.llm_semantics import (
    _preserve_safe_route,
    _reconcile_interpretation,
    _validation_summary,
)
from ticket_support_ai.schemas import (
    AnomalyQueryRequest,
    ClarificationRequest,
    QueryIntent,
    QueryRequest,
    UnsupportedRequest,
)

_ROUTE_ADAPTER = TypeAdapter(IntentRoute)
_REQUEST_ADAPTERS = {
    QueryIntent.ANALYTICS: TypeAdapter(AnalyticsPlan),
    QueryIntent.ANOMALIES: TypeAdapter(AnomalyQueryRequest),
    QueryIntent.CLARIFICATION: TypeAdapter(ClarificationRequest),
    QueryIntent.UNSUPPORTED: TypeAdapter(UnsupportedRequest),
}


class OllamaInterpreter:
    """Translate questions to the validated request union with local Qwen."""

    def __init__(
        self,
        settings: OllamaSettings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or OllamaSettings.from_environment()
        self._client = client

    async def interpret(self, question: str) -> QueryRequest:
        """Interpret one question, correcting invalid structured output once."""

        normalized = _validate_question(question, self.settings.max_question_chars)
        try:
            async with asyncio.timeout(self.settings.request_timeout_seconds):
                return await self._interpret_validated(normalized)
        except TimeoutError as exc:
            raise OllamaTimeoutError(
                f"Qwen interpretation exceeded the total "
                f"{self.settings.request_timeout_seconds:g}-second query budget."
            ) from exc

    async def _interpret_validated(self, normalized: str) -> QueryRequest:
        """Run both schema-constrained stages inside the caller's time budget."""

        route = await self._structured_call(
            [
                {"role": "system", "content": ROUTER_PROMPT},
                {"role": "user", "content": normalized},
            ],
            _ROUTE_ADAPTER,
        )
        # Check capabilities after real model routing, before detail generation.
        limitation = capability_limitation(normalized)
        if limitation is not None:
            return limitation
        route = _preserve_safe_route(route, normalized)
        adapter = _REQUEST_ADAPTERS[route.intent]
        detail_prompt = (
            ANALYTICS_PLAN_PROMPT
            if route.intent is QueryIntent.ANALYTICS
            else SYSTEM_PROMPT
        )
        messages = [
            {
                "role": "system",
                "content": detail_prompt
                if route.intent is QueryIntent.ANALYTICS
                else (
                    f"{detail_prompt}\nThe required top-level intent is "
                    f"{route.intent.value}."
                ),
            },
            {"role": "user", "content": normalized},
        ]
        structured = await self._structured_call(messages, adapter)
        return _reconcile_interpretation(structured, normalized)

    async def _structured_call(
        self,
        messages: list[dict[str, str]],
        adapter: TypeAdapter,
    ) -> Any:
        """Request and validate one schema-bound object with a corrective retry."""

        validation_details = ""
        for attempt in range(self.settings.corrective_retries + 1):
            if attempt:
                record_retry()
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous JSON failed validation. Correct it and return "
                            "only one schema-valid JSON object. Validation summary: "
                            f"{validation_details}"
                        ),
                    }
                )
            content = await self._chat(messages, adapter.json_schema())
            try:
                return adapter.validate_json(content)
            except ValidationError as exc:
                record_validation_error("model_schema_validation")
                validation_details = _validation_summary(exc)
            except ValueError as exc:
                record_validation_error("model_invalid_json")
                validation_details = f"Invalid JSON: {str(exc)[:500]}"
            messages.append({"role": "assistant", "content": content})

        raise StructuredOutputError(
            "Qwen did not return a valid structured request after one correction attempt."
        )

    async def warmup(self) -> None:
        """Prime model loading and the router prompt within the normal time budget."""
        await self.interpret("How many tickets are currently open?")

    async def readiness(self) -> OllamaModelStatus:
        """Check whether Ollama is reachable and the configured model is installed."""

        try:
            tags = await self._request("GET", "/api/tags")
            version_payload = await self._request("GET", "/api/version")
        except (OllamaUnavailableError, OllamaTimeoutError) as exc:
            return OllamaModelStatus(
                model=self.settings.model,
                service_available=False,
                model_available=False,
                error=str(exc),
            )
        except LLMError as exc:
            return OllamaModelStatus(
                model=self.settings.model,
                service_available=True,
                model_available=False,
                error=str(exc),
            )

        installed = {
            str(item.get("name") or item.get("model") or "")
            for item in tags.get("models", [])
            if isinstance(item, dict)
        }
        available = self.settings.model in installed
        return OllamaModelStatus(
            model=self.settings.model,
            service_available=True,
            model_available=available,
            version=str(version_payload.get("version", "")) or None,
            error=None
            if available
            else f"Model {self.settings.model!r} is not installed.",
        )

    async def _chat(
        self,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any],
    ) -> str:
        started = perf_counter()
        try:
            payload = await self._request(
                "POST",
                "/api/chat",
                json={
                    "model": self.settings.model,
                    "messages": messages,
                    "stream": False,
                    "keep_alive": "10m",
                    "format": output_schema,
                    "options": {
                        "temperature": 0,
                        "seed": 0,
                        "num_ctx": self.settings.context_tokens,
                        "num_predict": self.settings.response_tokens,
                    },
                },
            )
        finally:
            record_model_latency((perf_counter() - started) * 1000.0)
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise OllamaResponseError("Ollama returned no assistant message content.")
        return content

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(
            self.settings.request_timeout_seconds,
            connect=self.settings.connect_timeout_seconds,
        )
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.base_url,
            timeout=timeout,
        )
        try:
            response = await client.request(method, path, json=json, timeout=timeout)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"Ollama exceeded the {self.settings.request_timeout_seconds:g}-second "
                "inference timeout."
            ) from exc
        except httpx.ConnectError as exc:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.settings.base_url}."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = _safe_error_detail(exc.response)
            if exc.response.status_code == 404 and "model" in detail.lower():
                raise OllamaModelNotFoundError(
                    f"Ollama model {self.settings.model!r} is not available."
                ) from exc
            raise OllamaResponseError(
                f"Ollama returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaResponseError("Ollama request failed.") from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise OllamaResponseError("Ollama returned a non-JSON response.") from exc
        if not isinstance(payload, dict):
            raise OllamaResponseError("Ollama returned an unexpected response shape.")
        return payload


def _validate_question(question: str, maximum_length: int) -> str:
    if not isinstance(question, str):
        raise QuestionValidationError("Question must be text.")
    normalized = question.strip()
    if not normalized:
        raise QuestionValidationError("Question must not be blank.")
    if len(normalized) > maximum_length:
        raise QuestionValidationError(
            f"Question must contain at most {maximum_length} characters."
        )
    return normalized


def _safe_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text[:500] or "unknown error"
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        return payload["error"][:500]
    return "unexpected error response"


__all__ = [
    "ANALYTICS_PLAN_PROMPT",
    "ROUTER_PROMPT",
    "SYSTEM_PROMPT",
    "AnalyticsPlan",
    "IntentRoute",
    "LLMError",
    "NumericConditionPlan",
    "OllamaInterpreter",
    "OllamaModelNotFoundError",
    "OllamaModelStatus",
    "OllamaResponseError",
    "OllamaTimeoutError",
    "OllamaUnavailableError",
    "QuestionValidationError",
    "StructuredOutputError",
]
