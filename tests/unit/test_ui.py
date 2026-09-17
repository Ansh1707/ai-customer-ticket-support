"""Tests for the API-only Streamlit client and interface states."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from ticket_support_ai.ui import (
    SAMPLE_QUESTIONS,
    TicketAPIClient,
    UIAPIError,
)


def test_api_client_sends_query_and_anomaly_contracts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    client = TicketAPIClient(
        "http://api.test/",
        transport=httpx.MockTransport(handler),
    )

    assert client.health() == {"ok": True}
    assert client.query(
        "Count tickets",
        "custom",
        "2024-04-05T00:00:00",
    ) == {"ok": True}
    assert client.anomalies(
        {"rule": "long_resolution", "period": None, "limit": 25}
    ) == {"ok": True}

    assert [request.url.path for request in requests] == [
        "/health",
        "/query",
        "/anomalies",
    ]
    assert json.loads(requests[1].content) == {
        "question": "Count tickets",
        "reference_mode": "custom",
        "custom_reference": "2024-04-05T00:00:00",
        "limit": 50,
        "offset": 0,
    }
    assert dict(requests[2].url.params) == {
        "rule": "long_resolution",
        "limit": "25",
    }


def test_api_client_surfaces_structured_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            503,
            json={
                "error": {
                    "code": "ollama_unavailable",
                    "message": "Start Ollama and retry.",
                    "details": [],
                }
            },
        )

    client = TicketAPIClient(
        "http://api.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(UIAPIError, match="Start Ollama") as captured:
        client.query("Count tickets")

    assert captured.value.code == "ollama_unavailable"
    assert captured.value.status_code == 503


def test_api_client_rejects_invalid_success_response() -> None:
    client = TicketAPIClient(
        "http://api.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="not json")
        ),
    )

    with pytest.raises(UIAPIError, match="invalid JSON") as captured:
        client.health()

    assert captured.value.code == "invalid_api_response"


@pytest.mark.parametrize("base_url", ["localhost:8000", "file:///tmp/api", ""])
def test_api_client_rejects_invalid_explicit_base_url(base_url: str) -> None:
    if base_url == "":
        base_url = "not-a-url"
    with pytest.raises(ValueError, match="absolute HTTP"):
        TicketAPIClient(base_url)


class FakeUIAPI:
    """Complete fake API used to exercise Streamlit widgets and rendering."""

    def __init__(self, *, query_error: UIAPIError | None = None) -> None:
        self.query_error = query_error
        self.query_calls: list[tuple[str, str, str | None, int, int]] = []
        self.anomaly_calls: list[dict[str, Any]] = []

    def health(self) -> dict[str, Any]:
        return {
            "status": "ready",
            "application": "ticket-support-ai",
            "version": "0.1.0",
            "dataset": {
                "available": True,
                "row_count": 500,
                "warning_count": 28,
                "source_sha256": "checksum",
                "error": None,
            },
            "model": {
                "provider": "ollama",
                "model": "qwen2.5:3b",
                "service_available": True,
                "model_available": True,
                "version": "test",
                "error": None,
            },
        }

    def query(
        self,
        question: str,
        reference_mode: str,
        custom_reference: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        self.query_calls.append(
            (question, reference_mode, custom_reference, limit, offset)
        )
        if self.query_error is not None:
            raise self.query_error
        clock = _reference_clock()
        return {
            "question": question,
            "answer": "111 tickets match the interpreted request.",
            "interpretation": {
                "intent": "analytics",
                "operation": "count",
                "filters": [],
            },
            "data": {
                "operation": "count",
                "value": 111,
                "reference_clock": clock,
                "applied_date_range": None,
            },
            "reference_clock": clock,
            "warnings": [],
        }

    def anomalies(self, params: dict[str, Any]) -> dict[str, Any]:
        self.anomaly_calls.append(params)
        return {
            "requested_rule": "all",
            "tickets": [
                {
                    "ticket_id": "TKT-108",
                    "created_at": "2024-03-30T12:41:00",
                    "category": "General",
                    "priority": "High",
                    "status": "Resolved",
                    "agent_id": "AGT-07",
                    "issue_summary": "Question about usage limits",
                    "resolution_time_hrs": 119.7,
                    "unresolved_age_hrs": None,
                    "flags": [
                        {
                            "rule": "long_resolution",
                            "observed_value_hrs": 119.7,
                            "threshold_hrs": 48.15,
                            "event_at": "2024-04-04T12:23:00",
                            "reason": "Resolution exceeded the IQR fence.",
                        }
                    ],
                }
            ],
            "matching_ticket_count": 1,
            "returned_count": 1,
            "rule_counts": {
                "long_resolution": 1,
                "overdue_high_priority": 0,
                "resolution_before_response": 0,
            },
            "long_resolution_baseline": {
                "sample_size": 327,
                "q1_hrs": 6.15,
                "q3_hrs": 22.95,
                "upper_fence_hrs": 48.15,
            },
            "overdue_threshold_hrs": 24.0,
            "offset": 0,
            "limit": 25,
            "truncated": False,
            "reference_clock": _reference_clock(),
            "applied_date_range": None,
        }


def _reference_clock() -> dict[str, Any]:
    return {
        "mode": "dataset",
        "timestamp": "2024-04-05T00:00:00",
        "dataset_default": "2024-04-05T00:00:00",
        "warnings": [],
    }


def _streamlit_test_script(client) -> None:
    from ticket_support_ai.ui import render_app

    render_app(client)


def _button(app: AppTest, label: str):
    return next(item for item in app.button if item.label == label)


def test_streamlit_query_and_anomaly_workflows_render_evidence() -> None:
    client = FakeUIAPI()
    app = AppTest.from_function(
        _streamlit_test_script,
        args=(client,),
        default_timeout=10,
    ).run()

    assert not app.exception
    assert app.title[0].value == "AI Customer Ticket Support"
    assert len(app.tabs) == 3
    assert tuple(app.selectbox[0].options) == SAMPLE_QUESTIONS

    _button(app, "Ask Qwen").click()
    app.run()
    assert not app.exception
    assert client.query_calls == [(SAMPLE_QUESTIONS[0], "dataset", None, 50, 0)]
    assert any("111 tickets" in item.value for item in app.success)
    assert any(item.value == "111" for item in app.metric)

    _button(app, "Load anomalies").click()
    app.run()
    assert not app.exception
    assert client.anomaly_calls[0]["rule"] == "all"
    assert client.anomaly_calls[0]["limit"] == 25
    assert any(item.value == "1" for item in app.metric)
    assert len(app.dataframe) == 1


def test_streamlit_displays_query_error_without_crashing() -> None:
    client = FakeUIAPI(
        query_error=UIAPIError("Start Ollama and retry.", code="ollama_unavailable")
    )
    app = AppTest.from_function(
        _streamlit_test_script,
        args=(client,),
        default_timeout=10,
    ).run()

    _button(app, "Ask Qwen").click()
    app.run()

    assert not app.exception
    assert any("Start Ollama" in item.value for item in app.error)


def test_custom_reference_controls_appear_before_query_submission() -> None:
    client = FakeUIAPI()
    app = AppTest.from_function(
        _streamlit_test_script,
        args=(client,),
        default_timeout=10,
    ).run()

    query_reference = next(
        item
        for item in app.selectbox
        if item.label == "Reference time" and item.key == "query_reference_mode"
    )
    query_reference.select("custom")
    app.run()

    assert not app.exception
    assert client.query_calls == []
    assert any(item.label == "Reference date" for item in app.date_input)
    assert any(item.label == "Reference clock time" for item in app.time_input)
