"""FastAPI application exposing health, query, and anomaly workflows."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Literal, Protocol
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ticket_support_ai import __version__
from ticket_support_ai.anomalies import detect_anomalies
from ticket_support_ai.database import (
    DEFAULT_DATABASE_PATH,
    read_ingestion_metadata,
    read_tickets,
)
from ticket_support_ai.dates import DateInterpretationError, resolve_reference_clock
from ticket_support_ai.diagnostics import (
    begin_request,
    end_request,
    log_request_completion,
    record_outcome,
    record_validation_error,
)
from ticket_support_ai.llm import (
    OllamaInterpreter,
    OllamaModelNotFoundError,
    OllamaModelStatus,
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    QuestionValidationError,
    StructuredOutputError,
)
from ticket_support_ai.query import QueryService, QuestionInterpreter
from ticket_support_ai.schemas import (
    AnomalyDetectionResult,
    AnomalyQueryRequest,
    AnomalyRule,
    NaturalLanguageQueryResult,
    ReferenceMode,
    RelativePeriod,
    TicketTimeField,
    TimeFilter,
)


class ReadinessInterpreter(QuestionInterpreter, Protocol):
    """Interpreter operations used by the API."""

    async def readiness(self) -> OllamaModelStatus:
        """Return local-model readiness without raising for normal outages."""


class QueryAPIRequest(BaseModel):
    """Validated public request for the natural-language endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=1, max_length=2000)
    reference_mode: ReferenceMode = ReferenceMode.DATASET
    custom_reference: datetime | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Question must not be blank.")
        return normalized

    @model_validator(mode="after")
    def valid_reference_selection(self) -> QueryAPIRequest:
        if self.reference_mode is ReferenceMode.CUSTOM:
            if self.custom_reference is None:
                raise ValueError(
                    "custom_reference is required when reference_mode is custom."
                )
        elif self.custom_reference is not None:
            raise ValueError(
                "custom_reference is accepted only when reference_mode is custom."
            )
        return self


class DatasetHealth(BaseModel):
    """Dataset readiness details returned by the health endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    row_count: int | None = None
    warning_count: int | None = None
    source_sha256: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Combined application, dataset, Ollama, and model readiness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "degraded"]
    application: str = "ticket-support-ai"
    version: str
    dataset: DatasetHealth
    model: OllamaModelStatus
    default_reference: datetime | None


class ErrorDetail(BaseModel):
    """Stable public error information without internal stack details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    details: tuple[dict[str, object], ...] = ()


class ErrorResponse(BaseModel):
    """Envelope shared by API error responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error: ErrorDetail


def create_app(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    *,
    interpreter: ReadinessInterpreter | None = None,
) -> FastAPI:
    """Create an independently testable API bound to one database snapshot."""

    resolved_database = Path(database_path).expanduser().resolve()
    selected_interpreter = interpreter or OllamaInterpreter()
    query_service = QueryService(resolved_database, interpreter=selected_interpreter)
    application = FastAPI(
        title="AI Customer Ticket Support API",
        version=__version__,
        description=(
            "Local Qwen interpretation with deterministic ticket analytics and "
            "explainable anomaly detection."
        ),
    )
    _install_error_handlers(application)

    @application.middleware("http")
    async def request_diagnostics(request: Request, call_next):
        request_id = uuid4().hex
        token = begin_request(request_id)
        started = perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                record_outcome("error", error_code="unhandled_exception")
                log_request_completion(
                    method=request.method,
                    path=request.url.path,
                    status_code=500,
                    total_latency_ms=(perf_counter() - started) * 1000.0,
                )
                raise
            response.headers["X-Request-ID"] = request_id
            log_request_completion(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                total_latency_ms=(perf_counter() - started) * 1000.0,
            )
            return response
        finally:
            end_request(token)

    @application.get(
        "/health",
        response_model=HealthResponse,
        summary="Check application, dataset, and local model readiness",
    )
    async def health() -> HealthResponse:
        dataset = _dataset_health(resolved_database)
        model = await selected_interpreter.readiness()
        ready = dataset.available and model.service_available and model.model_available
        default_reference = None
        if dataset.available:
            default_reference = resolve_reference_clock(
                read_tickets(resolved_database), ReferenceMode.DATASET
            ).timestamp
        result = HealthResponse(
            status="ready" if ready else "degraded",
            version=__version__,
            dataset=dataset,
            model=model,
            default_reference=default_reference,
        )
        record_outcome(result.status)
        return result

    @application.post(
        "/query",
        response_model=NaturalLanguageQueryResult,
        responses=_endpoint_error_responses(include_model_errors=True),
        summary="Answer a natural-language question about the ticket snapshot",
    )
    async def query_tickets(payload: QueryAPIRequest) -> NaturalLanguageQueryResult:
        result = await query_service.query(
            payload.question,
            reference_mode=payload.reference_mode,
            custom_reference=payload.custom_reference,
            limit=payload.limit,
            offset=payload.offset,
        )
        record_outcome(result.outcome.value)
        return result

    @application.get(
        "/anomalies",
        response_model=AnomalyDetectionResult,
        responses=_endpoint_error_responses(include_model_errors=False),
        summary="Return deterministic, explainable ticket anomalies",
    )
    async def anomalies(
        rule: AnomalyRule = AnomalyRule.ALL,
        period: RelativePeriod | None = None,
        time_field: TicketTimeField | None = None,
        reference_mode: ReferenceMode = ReferenceMode.DATASET,
        custom_reference: datetime | None = None,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=1_000_000),
    ) -> AnomalyDetectionResult:
        _validate_reference_parameters(reference_mode, custom_reference)
        if time_field is not None and period is None:
            raise DateInterpretationError(
                "time_field can be supplied only when period is supplied."
            )
        selected_time_field = time_field
        if period is not None and selected_time_field is None:
            selected_time_field = _default_anomaly_time_field(rule)
        time_filter = (
            TimeFilter(field=selected_time_field, relative_period=period)
            if period is not None and selected_time_field is not None
            else None
        )
        anomaly_request = AnomalyQueryRequest(
            rule=rule,
            time_filter=time_filter,
            limit=limit,
            offset=offset,
        )
        tickets = read_tickets(resolved_database)
        reference_clock = resolve_reference_clock(
            tickets,
            reference_mode,
            custom_reference=custom_reference,
        )
        result = detect_anomalies(
            resolved_database, anomaly_request, reference_clock
        )
        record_outcome("ok")
        return result

    return application


def _dataset_health(database_path: Path) -> DatasetHealth:
    try:
        metadata = read_ingestion_metadata(database_path)
        actual_count = len(read_tickets(database_path))
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        return DatasetHealth(available=False, error=str(exc))
    if actual_count != metadata.row_count:
        return DatasetHealth(
            available=False,
            row_count=actual_count,
            warning_count=metadata.warning_count,
            source_sha256=metadata.source_sha256,
            error=(
                "Dataset row count does not match ingestion metadata: "
                f"expected {metadata.row_count}, found {actual_count}."
            ),
        )
    return DatasetHealth(
        available=True,
        row_count=actual_count,
        warning_count=metadata.warning_count,
        source_sha256=metadata.source_sha256,
    )


def _validate_reference_parameters(
    reference_mode: ReferenceMode,
    custom_reference: datetime | None,
) -> None:
    if reference_mode is ReferenceMode.CUSTOM and custom_reference is None:
        raise DateInterpretationError(
            "custom_reference is required when reference_mode is custom."
        )
    if reference_mode is not ReferenceMode.CUSTOM and custom_reference is not None:
        raise DateInterpretationError(
            "custom_reference is accepted only when reference_mode is custom."
        )


def _default_anomaly_time_field(rule: AnomalyRule) -> TicketTimeField:
    if rule in {
        AnomalyRule.LONG_RESOLUTION,
        AnomalyRule.RESOLUTION_BEFORE_RESPONSE,
    }:
        return TicketTimeField.RESOLVED_AT
    return TicketTimeField.CREATED_AT


def _endpoint_error_responses(*, include_model_errors: bool) -> dict[int, dict]:
    responses: dict[int, dict] = {
        422: {"model": ErrorResponse, "description": "Invalid request"},
        503: {"model": ErrorResponse, "description": "Dataset unavailable"},
    }
    if include_model_errors:
        responses[502] = {
            "model": ErrorResponse,
            "description": "Invalid local-model response",
        }
        responses[503] = {
            "model": ErrorResponse,
            "description": "Dataset or local model unavailable",
        }
        responses[504] = {
            "model": ErrorResponse,
            "description": "Local-model timeout",
        }
    return responses


def _install_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(RequestValidationError)
    async def request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        record_validation_error("api_request_validation")
        details = tuple(
            {
                "location": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in exc.errors()
        )
        return _error_response(
            422,
            "validation_error",
            "Request validation failed.",
            details,
        )

    @application.exception_handler(QuestionValidationError)
    async def question_validation_error(
        request: Request,
        exc: QuestionValidationError,
    ) -> JSONResponse:
        del request
        record_validation_error("question_validation")
        return _error_response(422, "invalid_question", str(exc))

    @application.exception_handler(DateInterpretationError)
    async def date_interpretation_error(
        request: Request,
        exc: DateInterpretationError,
    ) -> JSONResponse:
        del request
        record_validation_error("date_validation")
        return _error_response(422, "invalid_date_selection", str(exc))

    @application.exception_handler(OllamaTimeoutError)
    async def ollama_timeout_error(
        request: Request,
        exc: OllamaTimeoutError,
    ) -> JSONResponse:
        del request
        return _error_response(504, "ollama_timeout", str(exc))

    @application.exception_handler(OllamaUnavailableError)
    async def ollama_unavailable_error(
        request: Request,
        exc: OllamaUnavailableError,
    ) -> JSONResponse:
        del request
        return _error_response(503, "ollama_unavailable", str(exc))

    @application.exception_handler(OllamaModelNotFoundError)
    async def ollama_model_not_found_error(
        request: Request,
        exc: OllamaModelNotFoundError,
    ) -> JSONResponse:
        del request
        return _error_response(503, "ollama_model_not_found", str(exc))

    @application.exception_handler(StructuredOutputError)
    async def structured_output_error(
        request: Request,
        exc: StructuredOutputError,
    ) -> JSONResponse:
        del request
        return _error_response(502, "invalid_model_output", str(exc))

    @application.exception_handler(OllamaResponseError)
    async def ollama_response_error(
        request: Request,
        exc: OllamaResponseError,
    ) -> JSONResponse:
        del request
        return _error_response(502, "ollama_response_error", str(exc))

    @application.exception_handler(FileNotFoundError)
    async def missing_database_error(
        request: Request,
        exc: FileNotFoundError,
    ) -> JSONResponse:
        del request, exc
        return _error_response(
            503,
            "dataset_unavailable",
            "The ticket dataset is not available.",
        )

    @application.exception_handler(RuntimeError)
    async def runtime_data_error(
        request: Request,
        exc: RuntimeError,
    ) -> JSONResponse:
        del request, exc
        return _error_response(
            503,
            "service_unavailable",
            "A required local service or dataset is unavailable.",
        )


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: tuple[dict[str, object], ...] = (),
) -> JSONResponse:
    record_outcome("error", error_code=code)
    payload = ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details)
    )
    return JSONResponse(
        status_code=status_code, content=payload.model_dump(mode="json")
    )


def database_path_from_environment() -> Path:
    """Resolve the runtime database override used by the single-command launcher."""

    return Path(
        os.getenv("TICKET_DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
    ).expanduser()


app = create_app(database_path_from_environment())
