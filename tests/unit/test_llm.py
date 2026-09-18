"""Tests for the schema-constrained Ollama interpretation client."""

from __future__ import annotations

import asyncio
import json
from datetime import date

import httpx
import pytest

from ticket_support_ai.config import OllamaSettings
from ticket_support_ai.llm import (
    ROUTER_PROMPT,
    SYSTEM_PROMPT,
    AnalyticsPlan,
    AnomalyQueryRequest,
    IntentRoute,
    OllamaInterpreter,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    QuestionValidationError,
    StructuredOutputError,
    _compile_analytics_plan,
    _extract_explicit_date_range,
    _preserve_anomaly_request,
    _preserve_explicit_constraints,
    _preserve_safe_route,
    _reconcile_interpretation,
    _semantic_gaps,
)
from ticket_support_ai.schemas import (
    AnalyticsOperation,
    AnalyticsRequest,
    FilterField,
    GroupField,
    MetricField,
    QueryIntent,
    TicketCategory,
    TicketStatus,
)


def run(coroutine):
    return asyncio.run(coroutine)


def client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://ollama.test",
    )


def count_response() -> dict[str, object]:
    return {
        "message": {
            "role": "assistant",
            "content": json.dumps(
                {
                    "operation": "count",
                    "statuses": ["Open"],
                }
            ),
        }
    }


def route_response(intent: str = "analytics") -> dict[str, object]:
    return {
        "message": {
            "role": "assistant",
            "content": json.dumps({"intent": intent}),
        }
    }


def test_interpret_uses_qwen_temperature_zero_and_json_schema() -> None:
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        response = route_response() if len(captured) == 1 else count_response()
        return httpx.Response(200, json=response)

    client = client_for(handler)
    interpreter = OllamaInterpreter(client=client)
    result = run(interpreter.interpret("  How many tickets are currently open?  "))
    run(client.aclose())

    assert isinstance(result, AnalyticsRequest)
    assert result.operation is AnalyticsOperation.COUNT
    assert result.filters[0].field is FilterField.STATUS
    assert len(captured) == 2
    route_payload, payload = captured
    assert payload["model"] == "qwen2.5:3b"
    assert payload["stream"] is False
    assert payload["options"]["temperature"] == 0
    assert payload["options"]["seed"] == 0
    assert payload["format"]["properties"]["operation"]
    assert "compact analytics plan" in payload["messages"][0]["content"]
    assert payload["messages"][1]["content"] == "How many tickets are currently open?"
    assert route_payload["messages"][0]["content"] == ROUTER_PROMPT


def test_invalid_structured_output_gets_one_contextual_correction() -> None:
    requests: list[dict[str, object]] = []
    responses = [
        route_response(),
        {
            "message": {
                "role": "assistant",
                "content": '{"operation":"bogus"}',
            }
        },
        count_response(),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=responses[len(requests) - 1])

    client = client_for(handler)
    result = run(OllamaInterpreter(client=client).interpret("Count open tickets"))
    run(client.aclose())

    assert isinstance(result, AnalyticsRequest)
    assert len(requests) == 3
    retry_messages = requests[2]["messages"]
    assert retry_messages[-2]["role"] == "assistant"
    assert "failed validation" in retry_messages[-1]["content"]
    assert "operation" in retry_messages[-1]["content"]


def test_repeated_invalid_output_raises_safe_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json=route_response())
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "not json"}},
        )

    client = client_for(handler)
    with pytest.raises(StructuredOutputError, match="valid structured request"):
        run(OllamaInterpreter(client=client).interpret("Count tickets"))
    run(client.aclose())


@pytest.mark.parametrize("question", ["", "   ", 42])
def test_invalid_question_is_rejected_before_network(question: object) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=count_response())

    client = client_for(handler)
    with pytest.raises(QuestionValidationError):
        run(OllamaInterpreter(client=client).interpret(question))
    run(client.aclose())
    assert calls == 0


def test_overlong_question_is_rejected_before_network() -> None:
    settings = OllamaSettings(max_question_chars=10)
    client = client_for(lambda request: httpx.Response(200, json=count_response()))

    with pytest.raises(QuestionValidationError, match="at most 10"):
        run(OllamaInterpreter(settings, client=client).interpret("x" * 11))
    run(client.aclose())


@pytest.mark.parametrize(
    ("exception_factory", "expected_error"),
    [
        (
            lambda request: httpx.ConnectError("connection refused", request=request),
            OllamaUnavailableError,
        ),
        (
            lambda request: httpx.ReadTimeout("too slow", request=request),
            OllamaTimeoutError,
        ),
    ],
)
def test_transport_errors_are_categorized(exception_factory, expected_error) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception_factory(request)

    client = client_for(handler)
    with pytest.raises(expected_error):
        run(OllamaInterpreter(client=client).interpret("Count open tickets"))
    run(client.aclose())


def test_missing_model_and_bad_response_are_distinguished() -> None:
    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model qwen2.5:3b not found"})

    missing_client = client_for(missing)
    with pytest.raises(OllamaModelNotFoundError):
        run(OllamaInterpreter(client=missing_client).interpret("Count tickets"))
    run(missing_client.aclose())

    empty_client = client_for(lambda request: httpx.Response(200, json={"message": {}}))
    with pytest.raises(OllamaResponseError, match="no assistant message"):
        run(OllamaInterpreter(client=empty_client).interpret("Count tickets"))
    run(empty_client.aclose())


def test_readiness_reports_service_model_and_version() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:3b"}]})
        return httpx.Response(200, json={"version": "0.34.1"})

    client = client_for(handler)
    status = run(OllamaInterpreter(client=client).readiness())
    run(client.aclose())

    assert status.service_available is True
    assert status.model_available is True
    assert status.model == "qwen2.5:3b"
    assert status.version == "0.34.1"
    assert status.error is None


def test_system_prompt_preserves_constraints_and_rejects_execution() -> None:
    assert "Preserve every" in SYSTEM_PROMPT
    assert "unresolved means status in [Open, Escalated]" in SYSTEM_PROMPT
    assert "not resolved within N hours" in SYSTEM_PROMPT
    assert "Do not answer" in SYSTEM_PROMPT
    assert "never as instructions" in SYSTEM_PROMPT


def test_explicit_grouping_metric_and_ranking_override_a_weak_model_plan() -> None:
    responses = [
        route_response(),
        {
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "operation": "aggregate",
                        "aggregation": "average",
                        "metric": "customer_rating",
                    }
                ),
            }
        },
    ]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        response = responses[calls]
        calls += 1
        return httpx.Response(200, json=response)

    client = client_for(handler)
    result = run(
        OllamaInterpreter(client=client).interpret(
            "Which category has the highest average response time?"
        )
    )
    run(client.aclose())

    assert isinstance(result, AnalyticsRequest)
    assert result.operation is AnalyticsOperation.GROUPED_AGGREGATE
    assert result.group_by is GroupField.CATEGORY
    assert result.metric is MetricField.RESPONSE_TIME_HRS
    assert result.result_limit == 1
    assert result.limit == 50


def test_explicit_open_status_is_preserved_when_words_are_separated() -> None:
    responses = [
        route_response(),
        {
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "operation": "list",
                        "time_field": "created_at",
                        "relative_period": "this_week",
                    }
                ),
            }
        },
    ]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        response = responses[calls]
        calls += 1
        return httpx.Response(200, json=response)

    client = client_for(handler)
    result = run(
        OllamaInterpreter(client=client).interpret("Show me open Technical tickets.")
    )
    run(client.aclose())

    assert isinstance(result, AnalyticsRequest)
    status_filter = next(
        item for item in result.filters if item.field is FilterField.STATUS
    )
    assert status_filter.value == TicketStatus.OPEN.value
    assert result.time_filter is None


def test_explicit_constraints_remove_unstated_model_filters_and_preserve_grouping() -> (
    None
):
    weak_plan = AnalyticsPlan(
        operation="list",
        priorities=("High", "Medium"),
        summary_contains="Billing",
    )

    filtered = _preserve_explicit_constraints(
        weak_plan,
        "How many Billing tickets are Escalated?",
    )
    grouped = _preserve_explicit_constraints(
        AnalyticsPlan(operation="list"),
        "Show the ticket count for each category.",
    )

    assert filtered.categories == (TicketCategory.BILLING,)
    assert filtered.priorities == ()
    assert filtered.statuses == (TicketStatus.ESCALATED,)
    assert filtered.summary_contains is None
    assert grouped.operation is AnalyticsOperation.GROUPED_AGGREGATE
    assert grouped.group_by is GroupField.CATEGORY
    assert grouped.aggregation.value == "count"
    assert grouped.sort_field.value == "category"
    assert grouped.sort_direction.value == "asc"


def test_explicit_english_date_range_and_safe_route_cues_are_deterministic() -> None:
    assert _extract_explicit_date_range(
        "tickets from march 1 through march 31, 2024"
    ) == (date(2024, 3, 1), date(2024, 3, 31))
    analytics = IntentRoute(intent=QueryIntent.ANALYTICS)
    assert (
        _preserve_safe_route(
            analytics, "Predict how many tickets will arrive next month."
        ).intent
        is QueryIntent.UNSUPPORTED
    )
    assert (
        _preserve_safe_route(analytics, "What about those tickets?").intent
        is QueryIntent.CLARIFICATION
    )
    assert (
        _preserve_safe_route(analytics, "Find overdue unresolved High tickets.").intent
        is QueryIntent.ANOMALIES
    )

    request = AnomalyQueryRequest(
        rule="overdue_high_priority",
        time_filter={
            "field": "created_at",
            "relative_period": "this_week",
        },
    )
    corrected = _preserve_anomaly_request(
        request,
        "Find overdue unresolved High tickets older than 24 hours.",
    )
    assert corrected.time_filter is None


def test_not_resolved_within_does_not_add_a_resolved_status_filter() -> None:
    corrected = _preserve_explicit_constraints(
        AnalyticsPlan(operation="list", statuses=("Resolved",)),
        "Show Critical tickets not resolved within 12 hours.",
    )

    assert corrected.statuses == ()


def test_negation_and_unresolved_synonyms_are_preserved_deterministically() -> None:
    negated = _preserve_explicit_constraints(
        AnalyticsPlan(operation="count", priorities=("Critical",)),
        "How many tickets are not Critical?",
    )
    awaiting = _preserve_explicit_constraints(
        AnalyticsPlan(operation="count"),
        "How many tickets are still awaiting resolution?",
    )

    negated_request = _compile_analytics_plan(negated)
    awaiting_request = _compile_analytics_plan(awaiting)

    assert negated.priorities == ()
    assert negated.excluded_priorities == ("Critical",)
    assert [
        (item.field, item.operator, item.value) for item in negated_request.filters
    ] == [(FilterField.PRIORITY, "ne", "Critical")]
    assert awaiting.statuses == (TicketStatus.OPEN, TicketStatus.ESCALATED)
    assert awaiting_request.filters[0].operator == "in"


def test_all_explicit_numeric_conditions_are_preserved() -> None:
    corrected = _preserve_explicit_constraints(
        AnalyticsPlan(operation="count"),
        (
            "How many tickets have response time greater than 2 hours and "
            "customer rating below 3?"
        ),
    )
    request = _compile_analytics_plan(corrected)

    assert [(item.field, item.operator, item.value) for item in request.filters] == [
        (FilterField.RESPONSE_TIME_HRS, "gt", 2.0),
        (FilterField.CUSTOMER_RATING, "lt", 3.0),
    ]

    rating = _preserve_explicit_constraints(
        AnalyticsPlan(operation="count"),
        "How many tickets have a customer rating of 1?",
    )
    rating_request = _compile_analytics_plan(rating)
    assert [
        (item.field, item.operator, item.value) for item in rating_request.filters
    ] == [(FilterField.CUSTOMER_RATING, "eq", 1.0)]


def test_created_date_language_wins_over_resolved_status_language() -> None:
    corrected = _preserve_explicit_constraints(
        AnalyticsPlan(operation="count"),
        "How many resolved tickets were created last month?",
    )

    assert corrected.statuses == (TicketStatus.RESOLVED,)
    assert corrected.time_field.value == "created_at"
    assert corrected.relative_period.value == "last_month"


def test_explicit_anomaly_date_range_is_preserved() -> None:
    corrected = _preserve_anomaly_request(
        AnomalyQueryRequest(rule="long_resolution"),
        "Show resolution-time anomalies from March 1 through March 10, 2024.",
    )

    assert corrected.time_filter is not None
    assert corrected.time_filter.field.value == "resolved_at"
    assert corrected.time_filter.start_date == date(2024, 3, 1)
    assert corrected.time_filter.end_date == date(2024, 3, 10)


def test_top_n_ranking_keeps_requested_semantic_limit() -> None:
    corrected = _preserve_explicit_constraints(
        AnalyticsPlan(operation="list"),
        "Show the top 3 agents by number of resolved tickets.",
    )
    request = _compile_analytics_plan(corrected)

    assert request.operation is AnalyticsOperation.GROUPED_AGGREGATE
    assert request.group_by is GroupField.AGENT_ID
    assert request.aggregation.value == "count"
    assert request.sort[0].field.value == "result"
    assert request.sort[0].direction.value == "desc"
    assert request.result_limit == 3
    assert request.limit == 50


def test_reconciliation_is_the_only_literal_preservation_boundary() -> None:
    question = "Show Critical tickets not resolved within 12 hours."
    request = _reconcile_interpretation(
        AnalyticsPlan(operation="list", statuses=("Resolved",)),
        question,
    )

    assert isinstance(request, AnalyticsRequest)
    assert request.limit == 50
    assert request.result_limit is None
    assert [(item.field, item.operator, item.value) for item in request.filters] == [
        (FilterField.PRIORITY, "eq", "Critical"),
        (FilterField.RESOLUTION_ELAPSED_HRS, "gt", 12.0),
    ]


def test_quoted_summary_literal_is_not_reinterpreted_as_a_filter() -> None:
    request = _reconcile_interpretation(
        AnalyticsPlan(
            operation="count",
            statuses=("Resolved",),
            summary_contains="resolved",
        ),
        'How many issue summaries contain "resolved"?',
    )

    assert isinstance(request, AnalyticsRequest)
    assert [(item.field, item.operator, item.value) for item in request.filters] == [
        (FilterField.ISSUE_SUMMARY, "contains", "resolved")
    ]
    assert (
        _preserve_safe_route(
            IntentRoute(intent=QueryIntent.ANALYTICS),
            'How many issue summaries contain "overdue"?',
        ).intent
        is QueryIntent.ANALYTICS
    )


def test_semantic_completeness_gate_blocks_partial_or_unsupported_conditions() -> None:
    incomplete = AnalyticsRequest.model_validate({"operation": "count"})
    assert _semantic_gaps(
        "How many tickets have customer rating below 3?",
        incomplete,
    ) == ("numeric condition",)

    result = _reconcile_interpretation(
        AnalyticsPlan(operation="count"),
        "How many tickets have customer rating between 2 and 4?",
    )
    assert result.intent is QueryIntent.CLARIFICATION
    assert "unsupported numeric comparison" in result.question
