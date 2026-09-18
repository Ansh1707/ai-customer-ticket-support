"""Tests for parameterized deterministic analytics execution."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pytest

from ticket_support_ai.analytics import execute_analytics
from ticket_support_ai.database import database_connection, ingest_csv_snapshot
from ticket_support_ai.dates import resolve_reference_clock
from ticket_support_ai.ingestion import EXPECTED_COLUMNS, validate_csv
from ticket_support_ai.schemas import (
    AggregateAnalyticsResult,
    AnalyticsRequest,
    CountAnalyticsResult,
    GroupedAnalyticsResult,
    ListAnalyticsResult,
    OutputField,
    ReferenceClock,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = PROJECT_ROOT / "support_tickets.csv"


@pytest.fixture(scope="module")
def analytics_context(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, ReferenceClock]:
    database = tmp_path_factory.mktemp("analytics") / "tickets.db"
    validated = validate_csv(SOURCE_CSV)
    ingest_csv_snapshot(SOURCE_CSV, database)
    return database, resolve_reference_clock(validated.tickets)


def request(payload: dict[str, object]) -> AnalyticsRequest:
    return AnalyticsRequest.model_validate(payload)


def test_counts_open_all_unresolved_and_critical_unresolved_tickets(
    analytics_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = analytics_context

    open_result = execute_analytics(
        database,
        request(
            {
                "operation": "count",
                "filters": [{"field": "status", "operator": "eq", "value": "Open"}],
            }
        ),
        clock,
    )
    unresolved_result = execute_analytics(
        database,
        request(
            {
                "operation": "count",
                "filters": [
                    {
                        "field": "status",
                        "operator": "in",
                        "values": ["Open", "Escalated"],
                    }
                ],
            }
        ),
        clock,
    )
    critical_result = execute_analytics(
        database,
        request(
            {
                "operation": "count",
                "filters": [
                    {
                        "field": "priority",
                        "operator": "eq",
                        "value": "Critical",
                    },
                    {
                        "field": "status",
                        "operator": "in",
                        "values": ["Open", "Escalated"],
                    },
                ],
            }
        ),
        clock,
    )

    assert isinstance(open_result, CountAnalyticsResult)
    assert open_result.value == 111
    assert isinstance(unresolved_result, CountAnalyticsResult)
    assert unresolved_result.value == 173
    assert isinstance(critical_result, CountAnalyticsResult)
    assert critical_result.value == 31


def test_count_returns_zero_when_no_rows_match(
    analytics_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = analytics_context
    result = execute_analytics(
        database,
        request(
            {
                "operation": "count",
                "filters": [
                    {"field": "ticket_id", "operator": "eq", "value": "NO-SUCH-ID"}
                ],
            }
        ),
        clock,
    )

    assert isinstance(result, CountAnalyticsResult)
    assert result.value == 0


def test_average_is_null_safe_and_reports_contribution_count(
    analytics_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = analytics_context
    result = execute_analytics(
        database,
        request(
            {
                "operation": "aggregate",
                "aggregation": "average",
                "metric": "customer_rating",
                "filters": [
                    {"field": "category", "operator": "eq", "value": "Technical"}
                ],
            }
        ),
        clock,
    )

    assert isinstance(result, AggregateAnalyticsResult)
    assert result.value == pytest.approx(3.7403846153846154)
    assert result.matched_row_count == 152
    assert result.contributing_count == 104


def test_empty_aggregate_returns_none_and_zero_contributions(
    analytics_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = analytics_context
    result = execute_analytics(
        database,
        request(
            {
                "operation": "aggregate",
                "aggregation": "average",
                "metric": "customer_rating",
                "filters": [
                    {"field": "ticket_id", "operator": "eq", "value": "NO-SUCH-ID"}
                ],
            }
        ),
        clock,
    )

    assert isinstance(result, AggregateAnalyticsResult)
    assert result.value is None
    assert result.matched_row_count == 0
    assert result.contributing_count == 0


def test_grouped_average_returns_deterministic_lowest_agent(
    analytics_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = analytics_context
    result = execute_analytics(
        database,
        request(
            {
                "operation": "grouped_aggregate",
                "aggregation": "average",
                "metric": "customer_rating",
                "group_by": "agent_id",
                "sort": [{"field": "result", "direction": "asc"}],
                "result_limit": 1,
            }
        ),
        clock,
    )

    assert isinstance(result, GroupedAnalyticsResult)
    assert result.matching_group_count == 12
    assert result.returned_count == 1
    assert result.rows[0].group_value == "AGT-08"
    assert result.rows[0].value == pytest.approx(3.48)
    assert result.rows[0].contributing_count == 25


def test_relative_resolution_periods_rank_agents_correctly(
    analytics_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = analytics_context
    base = {
        "operation": "grouped_aggregate",
        "aggregation": "count",
        "group_by": "agent_id",
        "filters": [{"field": "status", "operator": "eq", "value": "Resolved"}],
        "sort": [{"field": "result", "direction": "desc"}],
        "result_limit": 1,
    }
    this_month = execute_analytics(
        database,
        request(
            {
                **base,
                "time_filter": {
                    "field": "resolved_at",
                    "relative_period": "this_month",
                },
            }
        ),
        clock,
    )
    last_month = execute_analytics(
        database,
        request(
            {
                **base,
                "time_filter": {
                    "field": "resolved_at",
                    "relative_period": "last_month",
                },
            }
        ),
        clock,
    )

    assert isinstance(this_month, GroupedAnalyticsResult)
    assert this_month.rows[0].group_value == "AGT-07"
    assert this_month.rows[0].value == 1
    assert isinstance(last_month, GroupedAnalyticsResult)
    assert last_month.rows[0].group_value == "AGT-01"
    assert last_month.rows[0].value == 16
    assert last_month.applied_date_range is not None
    assert last_month.applied_date_range.start == datetime.fromisoformat("2024-03-01")
    assert last_month.applied_date_range.end == datetime.fromisoformat("2024-04-01")


def test_critical_tickets_over_twelve_elapsed_hours_include_unresolved_age(
    analytics_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = analytics_context
    result = execute_analytics(
        database,
        request(
            {
                "operation": "list",
                "selected_fields": [
                    "ticket_id",
                    "status",
                    "resolution_time_hrs",
                    "unresolved_age_hrs",
                    "resolution_elapsed_hrs",
                ],
                "filters": [
                    {
                        "field": "priority",
                        "operator": "eq",
                        "value": "Critical",
                    },
                    {
                        "field": "resolution_elapsed_hrs",
                        "operator": "gt",
                        "value": 12,
                    },
                ],
                "sort": [{"field": "resolution_elapsed_hrs", "direction": "desc"}],
                "limit": 100,
            }
        ),
        clock,
    )

    assert isinstance(result, ListAnalyticsResult)
    assert result.matching_count == 34
    assert result.returned_count == 34
    assert all(
        float(row.values[OutputField.RESOLUTION_ELAPSED_HRS]) > 12
        for row in result.rows
    )
    assert any(
        row.values[OutputField.UNRESOLVED_AGE_HRS] is not None for row in result.rows
    )


def test_elapsed_filter_excludes_exact_twelve_hours_and_future_tickets(
    tmp_path: Path,
) -> None:
    source = tmp_path / "elapsed-boundary.csv"
    database = tmp_path / "elapsed-boundary.db"
    rows = [
        _valid_row(
            "TKT-RESOLVED-EXACT",
            resolution_time_hrs="12.0",
        ),
        _valid_row(
            "TKT-RESOLVED-OVER",
            resolution_time_hrs="12.01",
        ),
        _valid_row(
            "TKT-OPEN-EXACT",
            created_at="2024-03-01 12:00",
            status="Open",
            resolution_time_hrs="",
            customer_rating="",
        ),
        _valid_row(
            "TKT-OPEN-OVER",
            created_at="2024-03-01 11:59",
            status="Open",
            resolution_time_hrs="",
            customer_rating="",
        ),
        _valid_row(
            "TKT-FUTURE",
            created_at="2024-03-02 00:01",
            status="Open",
            resolution_time_hrs="",
            customer_rating="",
        ),
    ]
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    ingest_csv_snapshot(source, database)
    reference = datetime.fromisoformat("2024-03-02T00:00:00")
    clock = ReferenceClock(
        mode="custom",
        timestamp=reference,
        dataset_default=reference,
    )

    result = execute_analytics(
        database,
        request(
            {
                "operation": "list",
                "selected_fields": ["ticket_id", "resolution_elapsed_hrs"],
                "filters": [
                    {
                        "field": "resolution_elapsed_hrs",
                        "operator": "gt",
                        "value": 12,
                    }
                ],
                "sort": [{"field": "ticket_id", "direction": "asc"}],
            }
        ),
        clock,
    )

    assert isinstance(result, ListAnalyticsResult)
    assert [row.values[OutputField.TICKET_ID] for row in result.rows] == [
        "TKT-OPEN-OVER",
        "TKT-RESOLVED-OVER",
    ]
    assert all(
        float(row.values[OutputField.RESOLUTION_ELAPSED_HRS]) > 12
        for row in result.rows
    )


def test_list_pagination_uses_full_match_count_and_stable_order(
    analytics_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = analytics_context
    base = {
        "operation": "list",
        "selected_fields": ["ticket_id"],
        "filters": [{"field": "status", "operator": "eq", "value": "Open"}],
        "limit": 10,
    }
    first = execute_analytics(database, request(base), clock)
    second = execute_analytics(database, request({**base, "offset": 10}), clock)

    assert isinstance(first, ListAnalyticsResult)
    assert isinstance(second, ListAnalyticsResult)
    assert first.matching_count == second.matching_count == 111
    assert first.returned_count == second.returned_count == 10
    assert first.truncated is second.truncated is True
    assert {row.values[OutputField.TICKET_ID] for row in first.rows}.isdisjoint(
        row.values[OutputField.TICKET_ID] for row in second.rows
    )


def test_contains_filter_treats_sql_metacharacters_as_literal_data(
    analytics_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = analytics_context
    malicious = execute_analytics(
        database,
        request(
            {
                "operation": "count",
                "filters": [
                    {
                        "field": "issue_summary",
                        "operator": "contains",
                        "value": "%') OR 1=1 --",
                    }
                ],
            }
        ),
        clock,
    )

    assert isinstance(malicious, CountAnalyticsResult)
    assert malicious.value == 0
    with database_connection(database, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 500


def test_unresolved_rating_aggregate_distinguishes_matches_from_null_values(
    analytics_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = analytics_context
    result = execute_analytics(
        database,
        request(
            {
                "operation": "aggregate",
                "aggregation": "average",
                "metric": "customer_rating",
                "filters": [
                    {
                        "field": "status",
                        "operator": "in",
                        "values": ["Open", "Escalated"],
                    }
                ],
            }
        ),
        clock,
    )

    assert isinstance(result, AggregateAnalyticsResult)
    assert result.matched_row_count == 173
    assert result.contributing_count == 0
    assert result.value is None


def test_relative_time_filter_reports_applied_range(
    analytics_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = analytics_context
    result = execute_analytics(
        database,
        request(
            {
                "operation": "count",
                "time_filter": {
                    "field": "created_at",
                    "relative_period": "this_month",
                },
            }
        ),
        clock,
    )

    assert isinstance(result, CountAnalyticsResult)
    assert result.value == 0
    assert result.applied_date_range is not None
    assert result.applied_date_range.start == datetime.fromisoformat("2024-04-01")
    assert result.applied_date_range.end == datetime.fromisoformat("2024-04-05")


def test_result_ranking_keeps_all_groups_tied_at_limit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ties.csv"
    database = tmp_path / "ties.db"
    rows = [
        _valid_row("TKT-1", category="Billing"),
        _valid_row("TKT-2", category="Billing"),
        _valid_row("TKT-3", category="Technical"),
        _valid_row("TKT-4", category="Technical"),
        _valid_row("TKT-5", category="General"),
    ]
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    validated = validate_csv(source)
    ingest_csv_snapshot(source, database)
    clock = resolve_reference_clock(validated.tickets)

    result = execute_analytics(
        database,
        request(
            {
                "operation": "grouped_aggregate",
                "aggregation": "count",
                "group_by": "category",
                "sort": [{"field": "result", "direction": "desc"}],
                "result_limit": 1,
            }
        ),
        clock,
    )

    assert isinstance(result, GroupedAnalyticsResult)
    assert [(row.group_value, row.value) for row in result.rows] == [
        ("Billing", 2),
        ("Technical", 2),
    ]
    assert result.returned_count == 2
    assert result.matching_group_count == 3
    assert result.ties_extended is True
    assert result.truncated is True


def _valid_row(
    ticket_id: str,
    *,
    category: str = "Technical",
    **overrides: str,
) -> dict[str, str]:
    row = {
        "ticket_id": ticket_id,
        "created_at": "2024-03-01 10:00",
        "category": category,
        "priority": "Medium",
        "status": "Resolved",
        "response_time_hrs": "1.0",
        "resolution_time_hrs": "2.0",
        "agent_id": "AGT-01",
        "customer_rating": "4",
        "issue_summary": "Synthetic analytics test ticket",
    }
    row.update(overrides)
    return row
