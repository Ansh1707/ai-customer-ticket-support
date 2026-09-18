"""Capability boundaries must fail closed even with plausible model output."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from ticket_support_ai.capabilities import capability_limitation
from ticket_support_ai.database import ingest_csv_snapshot
from ticket_support_ai.llm import OllamaInterpreter
from ticket_support_ai.llm_plans import AnalyticsPlan
from ticket_support_ai.llm_semantics import _reconcile_interpretation
from ticket_support_ai.query import QueryService
from ticket_support_ai.schemas import ClarificationRequest


@pytest.mark.parametrize(
    "question",
    [
        "What is the median resolution time?",
        "What percentage of tickets are resolved?",
        "How many tickets are open or Technical?",
        "How many tickets were resolved in March but created in February 2024?",
        "Show 101 tickets",
        "Show 0 tickets",
        "How many tickets have rating above 3 or response time below 2?",
        "Give me the ratio of open to resolved tickets",
    ],
)
@pytest.mark.parametrize(
    "route", ["analytics", "anomalies", "clarification", "unsupported"]
)
def test_unsupported_capability_cannot_be_overridden_by_model(question, route):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200, json={"message": {"content": json.dumps({"intent": route})}}
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    )
    result = asyncio.run(OllamaInterpreter(client=client).interpret(question))
    assert isinstance(result, ClarificationRequest)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "question",
    [
        "How many High or Critical tickets are there?",
        "How many Open or Escalated tickets are there?",
        'How many summaries contain "median or percentage"?',
        "How many resolved tickets were created last month?",
    ],
)
def test_supported_contrasts_are_not_rejected(question):
    assert capability_limitation(question) is None


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    path = tmp_path_factory.mktemp("capabilities") / "tickets.db"
    ingest_csv_snapshot(
        Path(__file__).resolve().parents[2] / "support_tickets.csv", path
    )
    return path


@pytest.mark.parametrize(
    "question,expected",
    [
        ("How many tickets have no customer rating?", 173),
        ("How many tickets have a recorded customer rating?", 327),
        ("How many tickets have resolution time is null?", 173),
    ],
)
def test_null_filter_reconciliation_executes_correctly(database, question, expected):
    plan = _reconcile_interpretation(AnalyticsPlan(operation="count"), question)

    class Interpreter:
        async def interpret(self, _question):
            return plan

    result = asyncio.run(
        QueryService(database, interpreter=Interpreter()).query(question)
    )
    assert result.data.value == expected


@pytest.mark.parametrize(
    "question,plan,expected",
    [
        (
            "Show the 3 oldest unresolved tickets.",
            {"operation": "list"},
            ["TKT-054", "TKT-233", "TKT-289"],
        ),
        (
            "Which 5 agents have the fastest average response time?",
            {
                "operation": "grouped_aggregate",
                "group_by": "agent_id",
                "aggregation": "average",
                "metric": "response_time_hrs",
            },
            ["AGT-09", "AGT-10", "AGT-08", "AGT-02", "AGT-06"],
        ),
    ],
)
def test_numeric_result_limit_and_order(database, question, plan, expected):
    interpretation = _reconcile_interpretation(AnalyticsPlan(**plan), question)

    class Interpreter:
        async def interpret(self, _question):
            return interpretation

    result = asyncio.run(
        QueryService(database, interpreter=Interpreter()).query(question)
    )
    rows = result.data.rows
    actual = [
        row.group_value if hasattr(row, "group_value") else row.values["ticket_id"]
        for row in rows
    ]
    assert actual == expected
