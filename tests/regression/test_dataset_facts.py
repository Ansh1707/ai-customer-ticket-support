"""Independent raw-CSV regression calculations for PLAN.md Step 23."""

from __future__ import annotations

import csv
import hashlib
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = PROJECT_ROOT / "support_tickets.csv"
EXPECTED_SHA256 = "812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff"
REFERENCE = datetime(2024, 4, 5)  # noqa: DTZ001


def test_all_step_23_facts_from_unmodified_raw_csv() -> None:
    """Calculate every acceptance value without application analytics code."""

    assert hashlib.sha256(SOURCE_CSV.read_bytes()).hexdigest() == EXPECTED_SHA256
    with SOURCE_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 500
    assert sum(row["status"] == "Open" for row in rows) == 111
    assert sum(row["status"] in {"Open", "Escalated"} for row in rows) == 173
    assert sum(
        row["priority"] == "Critical"
        and row["status"] in {"Open", "Escalated"}
        for row in rows
    ) == 31
    assert sum(
        row["category"] == "Billing" and row["status"] == "Escalated"
        for row in rows
    ) == 16
    assert sum(
        float(row["response_time_hrs"])
        for row in rows
        if row["priority"] == "Critical"
    ) == pytest.approx(147.8)
    technical_resolutions = [
        float(row["resolution_time_hrs"])
        for row in rows
        if row["category"] == "Technical" and row["resolution_time_hrs"]
    ]
    assert min(technical_resolutions) == 1.6
    all_resolutions = [
        float(row["resolution_time_hrs"])
        for row in rows
        if row["resolution_time_hrs"]
    ]
    assert max(all_resolutions) == 119.7
    assert {
        category: sum(row["category"] == category for row in rows)
        for category in ("Billing", "General", "Technical")
    } == {"Billing": 159, "General": 189, "Technical": 152}
    assert sum("dashboard" in row["issue_summary"].casefold() for row in rows) == 18
    assert sum("payment" in row["issue_summary"].casefold() for row in rows) == 47
    assert sum(
        datetime(2024, 3, 1)  # noqa: DTZ001
        <= datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M")  # noqa: DTZ007
        < datetime(2024, 3, 11)  # noqa: DTZ001
        for row in rows
    ) == 62

    technical_ratings = [
        int(row["customer_rating"])
        for row in rows
        if row["category"] == "Technical" and row["customer_rating"]
    ]
    assert len(technical_ratings) == 104
    assert sum(technical_ratings) / len(technical_ratings) == pytest.approx(
        3.7403846153846154
    )

    ratings_by_agent: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        if row["customer_rating"]:
            ratings_by_agent[row["agent_id"]].append(int(row["customer_rating"]))
    agent_averages = {
        agent: sum(ratings) / len(ratings)
        for agent, ratings in ratings_by_agent.items()
    }
    lowest_agent = min(agent_averages, key=agent_averages.__getitem__)
    assert lowest_agent == "AGT-08"
    assert agent_averages[lowest_agent] == pytest.approx(3.48)
    assert len(ratings_by_agent[lowest_agent]) == 25

    march_resolutions: dict[str, int] = defaultdict(int)
    resolution_durations: list[float] = []
    timing_inconsistencies = 0
    overdue_high_priority = 0
    critical_over_twelve = 0
    for row in rows:
        created_at = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M")  # noqa: DTZ007
        resolution = (
            float(row["resolution_time_hrs"])
            if row["resolution_time_hrs"]
            else None
        )
        response = float(row["response_time_hrs"])
        unresolved = row["status"] in {"Open", "Escalated"}
        age = (REFERENCE - created_at).total_seconds() / 3600

        if row["status"] == "Resolved" and resolution is not None:
            resolution_durations.append(resolution)
            resolved_at = created_at + timedelta(hours=resolution)
            if datetime(2024, 3, 1) <= resolved_at < datetime(2024, 4, 1):  # noqa: DTZ001
                march_resolutions[row["agent_id"]] += 1
        if resolution is not None and resolution < response:
            timing_inconsistencies += 1
        if (
            unresolved
            and row["priority"] in {"High", "Critical"}
            and age > 24
        ):
            overdue_high_priority += 1
        elapsed = resolution if row["status"] == "Resolved" else age
        if row["priority"] == "Critical" and elapsed is not None and elapsed > 12:
            critical_over_twelve += 1

    march_leader = max(march_resolutions, key=march_resolutions.__getitem__)
    assert march_leader == "AGT-01"
    assert march_resolutions[march_leader] == 16

    ordered = sorted(resolution_durations)
    q1 = _linear_quantile(ordered, 0.25)
    q3 = _linear_quantile(ordered, 0.75)
    upper_fence = q3 + 1.5 * (q3 - q1)
    assert q1 == pytest.approx(6.15)
    assert q3 == pytest.approx(22.95)
    assert upper_fence == pytest.approx(48.15)
    assert sum(value > upper_fence for value in ordered) == 21
    assert timing_inconsistencies == 28
    assert overdue_high_priority == 80
    assert critical_over_twelve == 34


def _linear_quantile(ordered: list[float], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
