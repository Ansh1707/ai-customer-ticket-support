"""Tests for the supported structured analytics request contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ticket_support_ai.schemas import (
    QUERY_REQUEST_ADAPTER,
    Aggregation,
    AnalyticsOperation,
    AnalyticsRequest,
    AnomalyQueryRequest,
    ClarificationRequest,
    FilterField,
    GroupField,
    MembershipFilter,
    NumericComparisonFilter,
    QueryIntent,
    SortDirection,
    SortField,
    SummaryContainsFilter,
    UnsupportedRequest,
    parse_query_request,
)


def test_parses_critical_unresolved_count_example() -> None:
    request = parse_query_request(
        {
            "intent": "analytics",
            "operation": "count",
            "filters": [
                {"field": "priority", "operator": "eq", "value": "Critical"},
                {
                    "field": "status",
                    "operator": "in",
                    "values": ["Open", "Escalated"],
                },
            ],
        }
    )

    assert isinstance(request, AnalyticsRequest)
    assert request.operation is AnalyticsOperation.COUNT
    assert len(request.filters) == 2
    assert isinstance(request.filters[1], MembershipFilter)
    assert request.filters[1].values == ("Open", "Escalated")


def test_list_request_supports_all_required_filter_shapes() -> None:
    request = AnalyticsRequest.model_validate(
        {
            "operation": "list",
            "selected_fields": [
                "ticket_id",
                "priority",
                "status",
                "resolution_time_hrs",
                "issue_summary",
            ],
            "filters": [
                {
                    "field": "priority",
                    "operator": "in",
                    "values": ["High", "Critical"],
                },
                {
                    "field": "resolution_time_hrs",
                    "operator": "gt",
                    "value": 12,
                },
                {"field": "customer_rating", "operator": "is_not_null"},
                {
                    "field": "issue_summary",
                    "operator": "contains",
                    "value": "timeout",
                },
            ],
            "time_filter": {
                "field": "resolved_at",
                "relative_period": "this_month",
            },
            "sort": [
                {"field": "resolution_time_hrs", "direction": "desc"},
                {"field": "ticket_id", "direction": "asc"},
            ],
            "limit": 25,
        }
    )

    assert isinstance(request.filters[1], NumericComparisonFilter)
    assert isinstance(request.filters[3], SummaryContainsFilter)
    assert request.filters[3].case_sensitive is False
    assert request.sort[0].direction is SortDirection.DESCENDING
    assert request.limit == 25


def test_aggregate_and_grouped_aggregate_contracts() -> None:
    aggregate = AnalyticsRequest.model_validate(
        {
            "operation": "aggregate",
            "aggregation": "average",
            "metric": "customer_rating",
            "filters": [
                {"field": "category", "operator": "eq", "value": "Technical"}
            ],
        }
    )
    grouped = AnalyticsRequest.model_validate(
        {
            "operation": "grouped_aggregate",
            "aggregation": "count",
            "group_by": "agent_id",
            "filters": [
                {"field": "status", "operator": "eq", "value": "Resolved"}
            ],
            "time_filter": {
                "field": "resolved_at",
                "relative_period": "this_month",
            },
            "sort": [{"field": "result", "direction": "desc"}],
            "limit": 12,
        }
    )

    assert aggregate.aggregation is Aggregation.AVERAGE
    assert grouped.group_by is GroupField.AGENT_ID
    assert grouped.sort[0].field is SortField.RESULT
    assert grouped.metric is None


def test_non_analytics_intents_are_discriminated() -> None:
    anomaly = parse_query_request(
        {"intent": "anomalies", "rule": "long_resolution"}
    )
    clarification = parse_query_request(
        {
            "intent": "clarification",
            "question": "What does best mean: rating, speed, or volume?",
            "reason": "The ranking metric is ambiguous.",
        }
    )
    unsupported = parse_query_request(
        {
            "intent": "unsupported",
            "reason": "Ticket mutation is outside the analytics scope.",
        }
    )

    assert isinstance(anomaly, AnomalyQueryRequest)
    assert isinstance(clarification, ClarificationRequest)
    assert isinstance(unsupported, UnsupportedRequest)
    assert anomaly.intent is QueryIntent.ANOMALIES


def test_anomaly_request_pagination_is_bounded() -> None:
    request = AnomalyQueryRequest.model_validate(
        {"rule": "all", "limit": 25, "offset": 50}
    )

    assert request.limit == 25
    assert request.offset == 50
    with pytest.raises(ValidationError):
        AnomalyQueryRequest.model_validate({"offset": 1_000_001})


@pytest.mark.parametrize(
    "payload",
    [
        {
            "operation": "list",
            "selected_fields": [],
        },
        {
            "operation": "count",
            "selected_fields": ["ticket_id"],
        },
        {
            "operation": "aggregate",
            "aggregation": "average",
        },
        {
            "operation": "aggregate",
            "aggregation": "count",
            "metric": "customer_rating",
        },
        {
            "operation": "grouped_aggregate",
            "aggregation": "count",
            "group_by": "agent_id",
            "metric": "customer_rating",
        },
        {
            "operation": "grouped_aggregate",
            "aggregation": "average",
            "group_by": "agent_id",
        },
        {
            "operation": "grouped_aggregate",
            "aggregation": "count",
            "group_by": "agent_id",
            "sort": [{"field": "category"}],
        },
        {"operation": "count", "offset": 1},
        {"operation": "count", "limit": 1},
        {
            "operation": "aggregate",
            "aggregation": "average",
            "metric": "customer_rating",
            "offset": 1,
        },
    ],
)
def test_rejects_invalid_operation_combinations(payload: dict) -> None:
    with pytest.raises(ValidationError):
        AnalyticsRequest.model_validate(payload)


@pytest.mark.parametrize(
    "filter_payload",
    [
        {"field": "category", "operator": "gt", "value": 3},
        {"field": "status", "operator": "is_null"},
        {"field": "issue_summary", "operator": "in", "values": ["timeout"]},
        {"field": "priority", "operator": "eq", "value": "critical"},
        {"field": "status", "operator": "eq", "value": "Closed"},
        {"field": "customer_rating", "operator": "eq", "value": 6},
        {"field": "response_time_hrs", "operator": "lte", "value": -1},
        {"field": "agent_id", "operator": "eq", "value": ""},
        {"field": "issue_summary", "operator": "contains", "value": "  "},
        {
            "field": "priority",
            "operator": "in",
            "values": ["High", "High"],
        },
    ],
)
def test_rejects_invalid_filter_semantics(filter_payload: dict) -> None:
    with pytest.raises(ValidationError):
        AnalyticsRequest.model_validate(
            {
                "operation": "count",
                "filters": [filter_payload],
            }
        )


@pytest.mark.parametrize(
    "time_filter",
    [
        {"field": "created_at"},
        {
            "field": "created_at",
            "relative_period": "this_week",
            "start_date": "2024-03-01",
            "end_date": "2024-03-02",
        },
        {
            "field": "created_at",
            "start_date": "2024-03-02",
            "end_date": "2024-03-01",
        },
        {
            "field": "created_at",
            "start_date": "2024-03-01",
        },
    ],
)
def test_rejects_invalid_time_filter_forms(time_filter: dict) -> None:
    with pytest.raises(ValidationError):
        AnalyticsRequest.model_validate(
            {
                "operation": "count",
                "time_filter": time_filter,
            }
        )


def test_rejects_extra_fields_and_out_of_range_limit() -> None:
    with pytest.raises(ValidationError):
        AnalyticsRequest.model_validate(
            {"operation": "count", "limit": 101, "raw_sql": "DROP TABLE tickets"}
        )


def test_rejects_duplicate_selected_and_sort_fields() -> None:
    with pytest.raises(ValidationError):
        AnalyticsRequest.model_validate(
            {
                "operation": "list",
                "selected_fields": ["ticket_id", "ticket_id"],
            }
        )
    with pytest.raises(ValidationError):
        AnalyticsRequest.model_validate(
            {
                "operation": "list",
                "selected_fields": ["ticket_id"],
                "sort": [
                    {"field": "ticket_id", "direction": "asc"},
                    {"field": "ticket_id", "direction": "desc"},
                ],
            }
        )


def test_json_schema_exposes_all_intents_without_executable_fields() -> None:
    schema = QUERY_REQUEST_ADAPTER.json_schema()
    schema_text = str(schema)

    assert all(
        intent in schema_text
        for intent in ("analytics", "anomalies", "clarification", "unsupported")
    )
    assert all(
        operation in schema_text
        for operation in ("list", "count", "aggregate", "grouped_aggregate")
    )
    assert "raw_sql" not in schema_text
    assert "python" not in schema_text.lower()


def test_filter_field_enums_remain_allowlisted() -> None:
    assert set(FilterField) == {
        FilterField.TICKET_ID,
        FilterField.CATEGORY,
        FilterField.PRIORITY,
        FilterField.STATUS,
        FilterField.RESPONSE_TIME_HRS,
        FilterField.RESOLUTION_TIME_HRS,
        FilterField.AGENT_ID,
        FilterField.CUSTOMER_RATING,
        FilterField.ISSUE_SUMMARY,
        FilterField.RESOLUTION_ELAPSED_HRS,
    }
