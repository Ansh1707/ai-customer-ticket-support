"""Integration tests for interpretation-to-execution query orchestration."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from ticket_support_ai.database import ingest_csv_snapshot
from ticket_support_ai.query import QueryService
from ticket_support_ai.schemas import (
    AggregateAnalyticsResult,
    AnalyticsRequest,
    AnomalyDetectionResult,
    AnomalyQueryRequest,
    ClarificationRequest,
    CountAnalyticsResult,
    GroupedAnalyticsResult,
    ListAnalyticsResult,
    QueryRequest,
    ReferenceMode,
    UnsupportedRequest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = PROJECT_ROOT / "support_tickets.csv"


class StaticInterpreter:
    """Return a prevalidated interpretation without calling Ollama."""

    def __init__(self, result: QueryRequest) -> None:
        self.result = result
        self.questions: list[str] = []

    async def interpret(self, question: str) -> QueryRequest:
        self.questions.append(question)
        return self.result


@pytest.fixture(scope="module")
def database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("query-service") / "tickets.db"
    ingest_csv_snapshot(SOURCE_CSV, path)
    return path


def run_query(
    database: Path,
    question: str,
    interpretation: QueryRequest,
    **kwargs,
):
    interpreter = StaticInterpreter(interpretation)
    result = asyncio.run(
        QueryService(database, interpreter=interpreter).query(question, **kwargs)
    )
    assert interpreter.questions == [question]
    return result


def test_count_query_returns_answer_interpretation_and_evidence(database: Path) -> None:
    interpretation = AnalyticsRequest.model_validate(
        {
            "operation": "count",
            "filters": [{"field": "status", "operator": "eq", "value": "Open"}],
        }
    )

    result = run_query(
        database,
        "How many tickets are currently open?",
        interpretation,
    )

    assert result.answer == "111 tickets match the interpreted request."
    assert result.outcome.value == "ok"
    assert result.matching_count == 111
    assert result.timing.total_ms >= result.timing.interpretation_ms
    assert isinstance(result.data, CountAnalyticsResult)
    assert result.data.value == 111
    assert result.interpretation == interpretation
    assert result.reference_clock.timestamp == datetime.fromisoformat("2024-04-05")
    assert result.warnings == ()


def test_grouped_query_formats_leader_and_visible_date_range(database: Path) -> None:
    interpretation = AnalyticsRequest.model_validate(
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
            "limit": 1,
        }
    )

    result = run_query(
        database,
        "Which agent resolved the most tickets this month?",
        interpretation,
    )

    assert isinstance(result.data, GroupedAnalyticsResult)
    assert result.data.rows[0].group_value == "AGT-07"
    assert result.data.rows[0].value == 1
    assert result.answer.startswith(
        "The highest ticket count by agent id is 1 for AGT-07."
    )
    assert "2024-04-01 00:00 to 2024-04-05 00:00" in result.answer


def test_public_page_size_does_not_expand_semantic_top_n_limit(database: Path) -> None:
    interpretation = AnalyticsRequest.model_validate(
        {
            "operation": "grouped_aggregate",
            "aggregation": "count",
            "group_by": "agent_id",
            "filters": [{"field": "status", "operator": "eq", "value": "Resolved"}],
            "sort": [{"field": "result", "direction": "desc"}],
            "limit": 3,
        }
    )

    result = run_query(
        database,
        "Show the top 3 agents by number of resolved tickets.",
        interpretation,
        limit=50,
    )

    assert isinstance(result.data, GroupedAnalyticsResult)
    assert result.interpretation.limit == 3
    assert [(row.group_value, row.value) for row in result.data.rows] == [
        ("AGT-09", 37),
        ("AGT-12", 37),
        ("AGT-06", 34),
    ]


def test_list_and_aggregate_answers_retain_full_numeric_evidence(database: Path) -> None:
    list_request = AnalyticsRequest.model_validate(
        {
            "operation": "list",
            "selected_fields": [
                "ticket_id",
                "status",
                "resolution_elapsed_hrs",
            ],
            "filters": [
                {"field": "priority", "operator": "eq", "value": "Critical"},
                {
                    "field": "resolution_elapsed_hrs",
                    "operator": "gt",
                    "value": 12,
                },
            ],
            "limit": 100,
        }
    )
    average_request = AnalyticsRequest.model_validate(
        {
            "operation": "aggregate",
            "aggregation": "average",
            "metric": "customer_rating",
            "filters": [
                {"field": "category", "operator": "eq", "value": "Technical"}
            ],
        }
    )

    listed = run_query(database, "Show Critical tickets over 12 hours", list_request)
    averaged = run_query(database, "Average Technical rating", average_request)

    assert isinstance(listed.data, ListAnalyticsResult)
    assert listed.data.matching_count == 34
    assert listed.answer == (
        "Found and returned 34 matching tickets. "
        "Reference time: 2024-04-05 00:00 dataset-local."
    )
    assert isinstance(averaged.data, AggregateAnalyticsResult)
    assert averaged.data.value == pytest.approx(3.7403846153846154)
    assert averaged.data.contributing_count == 104
    assert (
        averaged.answer
        == "The average customer rating is 3.74, calculated from 104 values "
        "across 152 matching tickets."
    )


def test_anomaly_query_dispatches_to_deterministic_engine(database: Path) -> None:
    interpretation = AnomalyQueryRequest.model_validate(
        {
            "rule": "long_resolution",
            "time_filter": {
                "field": "resolved_at",
                "relative_period": "this_week",
            },
        }
    )

    result = run_query(
        database,
        "Are there anomalies in resolution times this week?",
        interpretation,
    )

    assert isinstance(result.data, AnomalyDetectionResult)
    assert result.data.matching_ticket_count == 1
    assert result.data.tickets[0].ticket_id == "TKT-108"
    assert result.answer.startswith(
        "Found 1 anomalous ticket (1 long-resolution)."
    )
    assert "this week" in result.answer


@pytest.mark.parametrize(
    ("interpretation", "expected_answer"),
    [
        (
            ClarificationRequest(
                question="Should best mean rating, speed, or ticket volume?",
                reason="The ranking metric is ambiguous.",
            ),
            "Should best mean rating, speed, or ticket volume?",
        ),
        (
            UnsupportedRequest(reason="Ticket deletion is outside analytics scope."),
            "This request is unsupported: Ticket deletion is outside analytics scope.",
        ),
    ],
)
def test_nonexecution_outcomes_have_no_data(
    database: Path,
    interpretation: QueryRequest,
    expected_answer: str,
) -> None:
    result = run_query(database, "User question", interpretation)

    assert result.answer == expected_answer
    assert result.data is None
    assert result.outcome.value == interpretation.intent.value
    assert result.matching_count is None


def test_custom_reference_warning_is_propagated(database: Path) -> None:
    interpretation = AnalyticsRequest.model_validate({"operation": "count"})

    result = run_query(
        database,
        "Count all tickets",
        interpretation,
        reference_mode=ReferenceMode.CUSTOM,
        custom_reference=datetime.fromisoformat("2024-03-01T00:00:00"),
    )

    assert isinstance(result.data, CountAnalyticsResult)
    assert result.data.value == 500
    assert len(result.warnings) == 1
    assert "precedes one or more recorded dataset events" in result.warnings[0]


def test_query_result_serializes_interpretation_and_typed_data(database: Path) -> None:
    interpretation = AnalyticsRequest.model_validate({"operation": "count"})
    result = run_query(database, "Count all tickets", interpretation)

    payload = result.model_dump(mode="json")

    assert payload["interpretation"]["intent"] == "analytics"
    assert payload["interpretation"]["operation"] == "count"
    assert payload["data"]["operation"] == "count"
    assert payload["data"]["value"] == 500
