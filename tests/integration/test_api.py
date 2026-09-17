"""HTTP-level integration tests for the FastAPI application."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx
import pytest

from ticket_support_ai.api import create_app, database_path_from_environment
from ticket_support_ai.database import ingest_csv_snapshot
from ticket_support_ai.diagnostics import LOGGER as DIAGNOSTICS_LOGGER
from ticket_support_ai.llm import (
    OllamaInterpreter,
    OllamaModelNotFoundError,
    OllamaModelStatus,
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    StructuredOutputError,
)
from ticket_support_ai.schemas import AnalyticsRequest, QueryRequest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = PROJECT_ROOT / "support_tickets.csv"


class FakeInterpreter:
    """Predictable model boundary for HTTP contract tests."""

    def __init__(
        self,
        result: QueryRequest | None = None,
        *,
        error: Exception | None = None,
        ready: bool = True,
    ) -> None:
        self.result = result or AnalyticsRequest.model_validate(
            {
                "operation": "count",
                "filters": [{"field": "status", "operator": "eq", "value": "Open"}],
            }
        )
        self.error = error
        self.ready = ready

    async def interpret(self, question: str) -> QueryRequest:
        del question
        if self.error is not None:
            raise self.error
        return self.result

    async def readiness(self) -> OllamaModelStatus:
        return OllamaModelStatus(
            model="qwen2.5:3b",
            service_available=self.ready,
            model_available=self.ready,
            version="test" if self.ready else None,
            error=None if self.ready else "Ollama is unavailable.",
        )


@pytest.fixture(scope="module")
def database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("api") / "tickets.db"
    ingest_csv_snapshot(SOURCE_CSV, path)
    return path


@pytest.fixture
def diagnostic_log(
    caplog: pytest.LogCaptureFixture,
) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger="ticket_support_ai.diagnostics")
    DIAGNOSTICS_LOGGER.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        DIAGNOSTICS_LOGGER.removeHandler(caplog.handler)


def request(app, method: str, url: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(send())


def test_health_reports_dataset_and_model_readiness(database: Path) -> None:
    response = request(
        create_app(database, interpreter=FakeInterpreter()), "GET", "/health"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["application"] == "ticket-support-ai"
    assert payload["dataset"]["available"] is True
    assert payload["dataset"]["row_count"] == 500
    assert payload["dataset"]["warning_count"] == 28
    assert payload["default_reference"] == "2024-04-05T00:00:00"
    assert payload["model"]["model"] == "qwen2.5:3b"
    assert payload["model"]["model_available"] is True


def test_health_is_degraded_but_successful_when_model_is_unavailable(
    database: Path,
) -> None:
    app = create_app(database, interpreter=FakeInterpreter(ready=False))
    response = request(app, "GET", "/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["dataset"]["available"] is True
    assert response.json()["model"]["service_available"] is False


def test_query_endpoint_returns_typed_answer_and_evidence(database: Path) -> None:
    app = create_app(database, interpreter=FakeInterpreter())
    response = request(
        app,
        "POST",
        "/query",
        json={"question": "How many tickets are currently open?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "111 tickets match the interpreted request."
    assert payload["outcome"] == "ok"
    assert payload["matching_count"] == 111
    assert payload["timing"]["total_ms"] >= payload["timing"]["interpretation_ms"]
    assert payload["interpretation"]["intent"] == "analytics"
    assert payload["data"]["operation"] == "count"
    assert payload["data"]["value"] == 111
    assert payload["reference_clock"]["timestamp"] == "2024-04-05T00:00:00"


def test_success_log_has_request_id_outcome_and_timings_without_question(
    database: Path,
    diagnostic_log: pytest.LogCaptureFixture,
) -> None:
    question = "How many tickets are currently open?"

    response = request(
        create_app(database, interpreter=FakeInterpreter()),
        "POST",
        "/query",
        json={"question": question},
    )

    event = _diagnostic_event(diagnostic_log)
    assert response.headers["X-Request-ID"] == event["request_id"]
    assert event["outcome"] == "ok"
    assert event["status_code"] == 200
    assert event["model_latency_ms"] == 0
    assert event["total_latency_ms"] >= 0
    assert event["retries"] == 0
    assert event["validation_errors"] == 0
    assert question not in diagnostic_log.text


def test_query_endpoint_exposes_custom_reference_warning(database: Path) -> None:
    app = create_app(database, interpreter=FakeInterpreter())
    response = request(
        app,
        "POST",
        "/query",
        json={
            "question": "How many tickets are currently open?",
            "reference_mode": "custom",
            "custom_reference": "2024-03-01T00:00:00",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reference_clock"]["mode"] == "custom"
    assert payload["reference_clock"]["timestamp"] == "2024-03-01T00:00:00"
    assert "historical status cannot be reconstructed" in payload["warnings"][0]


def test_query_endpoint_applies_public_pagination_after_interpretation(
    database: Path,
) -> None:
    interpretation = AnalyticsRequest.model_validate(
        {
            "operation": "list",
            "selected_fields": ["ticket_id"],
            "limit": 100,
        }
    )
    app = create_app(database, interpreter=FakeInterpreter(interpretation))

    response = request(
        app,
        "POST",
        "/query",
        json={"question": "List tickets", "limit": 7, "offset": 14},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["matching_count"] == 500
    assert payload["data"]["returned_count"] == 7
    assert payload["data"]["limit"] == 7
    assert payload["data"]["offset"] == 14
    assert payload["interpretation"]["limit"] == 7
    assert payload["interpretation"]["offset"] == 14


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "   "},
        {"question": "x" * 2001},
        {"question": "Count tickets", "unexpected": True},
        {"question": "Count tickets", "reference_mode": "custom"},
        {
            "question": "Count tickets",
            "reference_mode": "dataset",
            "custom_reference": "2024-04-05T00:00:00",
        },
    ],
)
def test_query_endpoint_rejects_invalid_public_input(
    database: Path,
    payload: dict[str, object],
) -> None:
    response = request(
        create_app(database, interpreter=FakeInterpreter()),
        "POST",
        "/query",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_anomaly_endpoint_supports_rule_period_reference_and_paging(
    database: Path,
) -> None:
    app = create_app(database, interpreter=FakeInterpreter(ready=False))
    response = request(
        app,
        "GET",
        "/anomalies",
        params={
            "rule": "long_resolution",
            "period": "this_week",
            "limit": 10,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["matching_ticket_count"] == 1
    assert payload["tickets"][0]["ticket_id"] == "TKT-108"
    assert payload["applied_date_range"]["label"] == "this week"
    assert payload["reference_clock"]["mode"] == "dataset"


def test_anomalies_remain_available_during_model_failure(database: Path) -> None:
    interpreter = FakeInterpreter(error=OllamaUnavailableError("Ollama is down."))
    app = create_app(database, interpreter=interpreter)

    query_response = request(
        app,
        "POST",
        "/query",
        json={"question": "Count open tickets"},
    )
    anomaly_response = request(
        app,
        "GET",
        "/anomalies",
        params={"rule": "overdue_high_priority", "limit": 100},
    )

    assert query_response.status_code == 503
    assert query_response.json()["error"]["code"] == "ollama_unavailable"
    assert anomaly_response.status_code == 200
    assert anomaly_response.json()["matching_ticket_count"] == 80


def test_anomaly_endpoint_exposes_data_quality_flags(database: Path) -> None:
    response = request(
        create_app(database, interpreter=FakeInterpreter(ready=False)),
        "GET",
        "/anomalies",
        params={"rule": "resolution_before_response", "limit": 100},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["matching_ticket_count"] == 28
    assert payload["rule_counts"]["resolution_before_response"] == 28
    assert all(
        row["resolution_time_hrs"] < row["response_time_hrs"]
        for row in payload["tickets"]
    )


@pytest.mark.parametrize(
    "params",
    [
        {"time_field": "created_at"},
        {"reference_mode": "custom"},
        {"reference_mode": "dataset", "custom_reference": "2024-04-05T00:00:00"},
        {"limit": 0},
        {"offset": -1},
    ],
)
def test_anomaly_endpoint_rejects_invalid_parameter_combinations(
    database: Path,
    params: dict[str, object],
) -> None:
    response = request(
        create_app(database, interpreter=FakeInterpreter()),
        "GET",
        "/anomalies",
        params=params,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] in {
        "invalid_date_selection",
        "validation_error",
    }


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (OllamaTimeoutError("timed out"), 504, "ollama_timeout"),
        (
            OllamaModelNotFoundError("model missing"),
            503,
            "ollama_model_not_found",
        ),
        (StructuredOutputError("bad output"), 502, "invalid_model_output"),
        (OllamaResponseError("bad response"), 502, "ollama_response_error"),
    ],
)
def test_query_model_failures_have_distinct_safe_errors(
    database: Path,
    error: Exception,
    status: int,
    code: str,
) -> None:
    app = create_app(database, interpreter=FakeInterpreter(error=error))
    response = request(
        app,
        "POST",
        "/query",
        json={"question": "Count tickets"},
    )

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "traceback" not in response.text.casefold()


def test_failed_model_validation_is_diagnosable_without_logging_content(
    database: Path,
    diagnostic_log: pytest.LogCaptureFixture,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = '{"intent":"analytics"}' if calls == 1 else "private bad output"
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": content}},
        )

    model_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://ollama.test",
    )
    app = create_app(database, interpreter=OllamaInterpreter(client=model_client))
    response = request(
        app,
        "POST",
        "/query",
        json={"question": "Private demonstration question"},
    )
    asyncio.run(model_client.aclose())

    event = _diagnostic_event(diagnostic_log)
    assert response.status_code == 502
    assert response.headers["X-Request-ID"] == event["request_id"]
    assert event["outcome"] == "error"
    assert event["error_code"] == "invalid_model_output"
    assert event["retries"] == 1
    assert event["validation_errors"] == 2
    assert event["validation_error_kinds"] == ["model_schema_validation"]
    assert event["model_latency_ms"] >= 0
    assert "Private demonstration question" not in diagnostic_log.text
    assert "private bad output" not in diagnostic_log.text


def test_missing_dataset_degrades_health_and_blocks_data_endpoints(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path / "missing.db", interpreter=FakeInterpreter())

    health = request(app, "GET", "/health")
    anomalies = request(app, "GET", "/anomalies")

    assert health.status_code == 200
    assert health.json()["status"] == "degraded"
    assert health.json()["dataset"]["available"] is False
    assert anomalies.status_code == 503
    assert anomalies.json()["error"]["code"] == "dataset_unavailable"


def test_openapi_documents_all_required_endpoints_and_constraints(
    database: Path,
) -> None:
    response = request(
        create_app(database, interpreter=FakeInterpreter()),
        "GET",
        "/openapi.json",
    )

    assert response.status_code == 200
    schema = response.json()
    assert {"/health", "/query", "/anomalies"} <= set(schema["paths"])
    query_schema = schema["components"]["schemas"]["QueryAPIRequest"]
    assert query_schema["properties"]["question"]["maxLength"] == 2000


def test_database_environment_override_is_resolved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = tmp_path / "custom.db"
    monkeypatch.setenv("TICKET_DATABASE_PATH", str(expected))

    assert database_path_from_environment().resolve() == expected.resolve()


def _diagnostic_event(caplog: pytest.LogCaptureFixture) -> dict[str, object]:
    messages = [
        record.message
        for record in caplog.records
        if record.name == "ticket_support_ai.diagnostics"
    ]
    assert len(messages) == 1
    event = json.loads(messages[0])
    assert event["event"] == "request_complete"
    return event
