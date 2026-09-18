"""Opt-in end-to-end checks from natural language through deterministic results."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from ticket_support_ai.database import ingest_csv_snapshot
from ticket_support_ai.query import QueryService
from ticket_support_ai.schemas import (
    AggregateAnalyticsResult,
    AnomalyDetectionResult,
    CountAnalyticsResult,
    GroupedAnalyticsResult,
    ListAnalyticsResult,
    QueryOutcome,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_OLLAMA") != "1",
        reason="set RUN_LIVE_OLLAMA=1 to call the local Ollama service",
    ),
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = PROJECT_ROOT / "support_tickets.csv"


@pytest.fixture(scope="module")
def service(tmp_path_factory: pytest.TempPathFactory) -> QueryService:
    database = tmp_path_factory.mktemp("live-query") / "tickets.db"
    ingest_csv_snapshot(SOURCE_CSV, database)
    return QueryService(database)


def ask(service: QueryService, question: str):
    return asyncio.run(service.query(question))


def test_live_open_ticket_answer(service: QueryService) -> None:
    result = ask(service, "How many tickets are currently open?")

    assert isinstance(result.data, CountAnalyticsResult)
    assert result.data.value == 111
    assert result.answer.startswith("111 tickets")


def test_live_monthly_agent_ranking(service: QueryService) -> None:
    result = ask(service, "Which agent resolved the most tickets this month?")

    assert isinstance(result.data, GroupedAnalyticsResult)
    assert [(row.group_value, row.value) for row in result.data.rows] == [("AGT-07", 1)]
    assert "AGT-07" in result.answer
    assert "2024-04-01" in result.answer


def test_live_critical_elapsed_ticket_list(service: QueryService) -> None:
    result = ask(
        service,
        "Show me all Critical tickets not resolved within 12 hours.",
    )

    assert isinstance(result.data, ListAnalyticsResult)
    assert result.data.matching_count == 34
    assert result.data.returned_count == 34
    assert result.answer.startswith("Found and returned 34 matching tickets.")
    assert "Reference time: 2024-04-05 00:00 dataset-local" in result.answer


def test_live_technical_rating_average(service: QueryService) -> None:
    result = ask(
        service,
        "What is the average customer rating for Technical category tickets?",
    )

    assert isinstance(result.data, AggregateAnalyticsResult)
    assert result.data.value == pytest.approx(3.7403846153846154)
    assert result.data.contributing_count == 104
    assert "3.74" in result.answer


def test_live_weekly_resolution_anomaly(service: QueryService) -> None:
    result = ask(service, "Are there any anomalies in resolution times this week?")

    assert isinstance(result.data, AnomalyDetectionResult)
    assert result.data.matching_ticket_count == 1
    assert result.data.tickets[0].ticket_id == "TKT-108"
    assert "1 anomalous ticket" in result.answer


def test_live_source_timing_inconsistencies(service: QueryService) -> None:
    result = ask(
        service,
        "Which records have resolution times shorter than first-response times?",
    )

    assert isinstance(result.data, AnomalyDetectionResult)
    assert result.data.matching_ticket_count == 28
    assert result.data.rule_counts.resolution_before_response == 28
    assert "28 timing-inconsistency" in result.answer


def test_live_regression_multi_priority_count(service: QueryService) -> None:
    result = ask(service, "How many High or Critical priority tickets are there?")

    assert isinstance(result.data, CountAnalyticsResult)
    assert result.data.value == 189


def test_live_regression_billing_resolution_average(service: QueryService) -> None:
    result = ask(service, "Find the mean resolution time for Billing cases.")

    assert isinstance(result.data, AggregateAnalyticsResult)
    assert result.data.value == pytest.approx(16.33465346534654)
    assert result.data.contributing_count == 101


def test_live_regression_filtered_list(service: QueryService) -> None:
    result = ask(service, "Show me open Technical tickets.")

    assert isinstance(result.data, ListAnalyticsResult)
    assert result.data.matching_count == 30


def test_live_regression_category_response_ranking(service: QueryService) -> None:
    result = ask(service, "Which category has the highest average response time?")

    assert isinstance(result.data, GroupedAnalyticsResult)
    assert result.data.rows[0].group_value == "Technical"
    assert result.data.rows[0].value == pytest.approx(2.6697368421052627)


def test_live_regression_creation_period_count(service: QueryService) -> None:
    result = ask(service, "How many tickets were created last month?")

    assert isinstance(result.data, CountAnalyticsResult)
    assert result.data.value == 188
    assert result.data.applied_date_range is not None
    assert result.data.applied_date_range.label == "last month"


def test_live_negated_priority_count(service: QueryService) -> None:
    result = ask(service, "How many tickets are not Critical?")

    assert isinstance(result.data, CountAnalyticsResult)
    assert result.data.value == 445


def test_live_unresolved_status_synonym(service: QueryService) -> None:
    result = ask(service, "How many tickets are still awaiting resolution?")

    assert isinstance(result.data, CountAnalyticsResult)
    assert result.data.value == 173


def test_live_explicit_created_period_with_resolved_status(
    service: QueryService,
) -> None:
    result = ask(service, "How many resolved tickets were created last month?")

    assert isinstance(result.data, CountAnalyticsResult)
    assert result.data.value == 121
    assert result.data.applied_date_range is not None
    assert result.data.applied_date_range.label == "last month"


def test_live_explicit_anomaly_date_range(service: QueryService) -> None:
    result = ask(
        service,
        "Show resolution-time anomalies from March 1 through March 10, 2024.",
    )

    assert isinstance(result.data, AnomalyDetectionResult)
    assert result.data.matching_ticket_count == 3
    assert result.data.applied_date_range is not None
    assert result.data.applied_date_range.label == "2024-03-01 through 2024-03-10"


def test_live_multiple_numeric_conditions(service: QueryService) -> None:
    result = ask(
        service,
        (
            "How many tickets have response time greater than 2 hours and "
            "customer rating below 3?"
        ),
    )

    assert isinstance(result.data, CountAnalyticsResult)
    assert result.data.value == 33


def test_live_top_three_resolved_agents(service: QueryService) -> None:
    result = ask(service, "Show the top 3 agents by number of resolved tickets.")

    assert isinstance(result.data, GroupedAnalyticsResult)
    assert [(row.group_value, row.value) for row in result.data.rows] == [
        ("AGT-09", 37),
        ("AGT-12", 37),
        ("AGT-06", 34),
    ]


def test_live_group_count_preserves_nonranking_order(service: QueryService) -> None:
    result = ask(service, "Show the ticket count for each category.")

    assert isinstance(result.data, GroupedAnalyticsResult)
    assert [(row.group_value, row.value) for row in result.data.rows] == [
        ("Billing", 159),
        ("General", 189),
        ("Technical", 152),
    ]


def test_live_exact_customer_rating_filter(service: QueryService) -> None:
    result = ask(service, "How many tickets have a customer rating of 1?")

    assert isinstance(result.data, CountAnalyticsResult)
    assert result.data.value == 14


def test_live_quoted_summary_value_is_only_literal_text(service: QueryService) -> None:
    result = ask(service, 'How many issue summaries contain "resolved"?')

    assert result.outcome is QueryOutcome.OK
    assert isinstance(result.data, CountAnalyticsResult)
    assert result.data.value == 0
    assert len(result.interpretation.filters) == 1
    summary_filter = result.interpretation.filters[0]
    assert summary_filter.field == "issue_summary"
    assert summary_filter.value == "resolved"


def test_live_unsupported_numeric_form_clarifies_without_execution(
    service: QueryService,
) -> None:
    result = ask(
        service,
        "How many tickets have customer rating between 2 and 4?",
    )

    assert result.outcome is QueryOutcome.CLARIFICATION
    assert result.data is None
    assert "unsupported numeric comparison" in result.answer
    assert result.timing.execution_ms == 0
