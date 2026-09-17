"""Tests for deterministic and explainable anomaly detection."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ticket_support_ai.anomalies import (
    OVERDUE_HIGH_PRIORITY_HOURS,
    calculate_iqr_baseline,
    detect_anomalies,
    detect_ticket_anomalies,
)
from ticket_support_ai.database import ingest_csv_snapshot
from ticket_support_ai.dates import resolve_reference_clock
from ticket_support_ai.ingestion import validate_csv
from ticket_support_ai.schemas import (
    AnomalyQueryRequest,
    AnomalyRule,
    ReferenceClock,
    ReferenceMode,
    TicketCategory,
    TicketPriority,
    TicketRecord,
    TicketStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = PROJECT_ROOT / "support_tickets.csv"


@pytest.fixture(scope="module")
def anomaly_context(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, ReferenceClock]:
    database = tmp_path_factory.mktemp("anomalies") / "tickets.db"
    validated = validate_csv(SOURCE_CSV)
    ingest_csv_snapshot(SOURCE_CSV, database)
    return database, resolve_reference_clock(validated.tickets)


def test_iqr_baseline_matches_independent_dataset_calculation(
    anomaly_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = anomaly_context
    result = detect_anomalies(
        database,
        AnomalyQueryRequest(rule=AnomalyRule.LONG_RESOLUTION, limit=100),
        clock,
    )

    baseline = result.long_resolution_baseline
    assert baseline is not None
    assert baseline.sample_size == 327
    assert baseline.quartile_method == "linear_type_7"
    assert baseline.q1_hrs == pytest.approx(6.15)
    assert baseline.q3_hrs == pytest.approx(22.95)
    assert baseline.iqr_hrs == pytest.approx(16.8)
    assert baseline.multiplier == 1.5
    assert baseline.upper_fence_hrs == pytest.approx(48.15)
    assert result.matching_ticket_count == 21
    assert result.rule_counts.long_resolution == 21
    assert result.rule_counts.overdue_high_priority == 0
    assert all(
        flag.rule is AnomalyRule.LONG_RESOLUTION
        and flag.observed_value_hrs > flag.threshold_hrs
        and "IQR" in flag.reason
        for ticket in result.tickets
        for flag in ticket.flags
    )


def test_overdue_high_priority_rule_uses_strict_twenty_four_hour_boundary(
    anomaly_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = anomaly_context
    result = detect_anomalies(
        database,
        AnomalyQueryRequest(rule=AnomalyRule.OVERDUE_HIGH_PRIORITY, limit=100),
        clock,
    )

    assert result.long_resolution_baseline is None
    assert result.overdue_threshold_hrs == OVERDUE_HIGH_PRIORITY_HOURS
    assert result.matching_ticket_count == 80
    assert result.rule_counts.long_resolution == 0
    assert result.rule_counts.overdue_high_priority == 80
    assert all(
        ticket.priority in {TicketPriority.HIGH, TicketPriority.CRITICAL}
        and ticket.status in {TicketStatus.OPEN, TicketStatus.ESCALATED}
        and ticket.unresolved_age_hrs is not None
        and ticket.unresolved_age_hrs > 24
        for ticket in result.tickets
    )


def test_data_quality_rule_preserves_and_explains_all_28_records(
    anomaly_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = anomaly_context
    result = detect_anomalies(
        database,
        AnomalyQueryRequest(
            rule=AnomalyRule.RESOLUTION_BEFORE_RESPONSE,
            limit=100,
        ),
        clock,
    )

    assert result.matching_ticket_count == 28
    assert result.rule_counts.resolution_before_response == 28
    assert all(
        ticket.resolution_time_hrs is not None
        and ticket.resolution_time_hrs < ticket.response_time_hrs
        and ticket.flags[0].rule is AnomalyRule.RESOLUTION_BEFORE_RESPONSE
        and "source-data inconsistency" in ticket.flags[0].reason
        for ticket in result.tickets
    )


def test_all_rules_return_unique_tickets_and_unpaginated_counts(
    anomaly_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = anomaly_context
    result = detect_anomalies(
        database,
        AnomalyQueryRequest(rule=AnomalyRule.ALL, limit=100),
        clock,
    )

    assert result.matching_ticket_count == 129
    assert result.returned_count == 100
    assert result.truncated is True
    assert result.rule_counts.long_resolution == 21
    assert result.rule_counts.overdue_high_priority == 80
    assert result.rule_counts.resolution_before_response == 28
    assert len({ticket.ticket_id for ticket in result.tickets}) == 100


def test_resolution_anomalies_this_week_use_inferred_resolution_time(
    anomaly_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = anomaly_context
    result = detect_anomalies(
        database,
        AnomalyQueryRequest.model_validate(
            {
                "rule": "long_resolution",
                "time_filter": {
                    "field": "resolved_at",
                    "relative_period": "this_week",
                },
            }
        ),
        clock,
    )

    assert result.matching_ticket_count == 1
    assert result.tickets[0].ticket_id == "TKT-108"
    assert result.tickets[0].resolution_time_hrs == 119.7
    assert result.applied_date_range is not None
    assert result.applied_date_range.start == datetime.fromisoformat("2024-04-01")
    assert result.applied_date_range.end == datetime.fromisoformat("2024-04-05")
    assert result.long_resolution_baseline is not None
    assert result.long_resolution_baseline.sample_size == 327


def test_anomaly_pagination_is_stable_and_counts_before_slicing(
    anomaly_context: tuple[Path, ReferenceClock],
) -> None:
    database, clock = anomaly_context
    first = detect_anomalies(
        database,
        AnomalyQueryRequest(rule=AnomalyRule.ALL, limit=10),
        clock,
    )
    second = detect_anomalies(
        database,
        AnomalyQueryRequest(rule=AnomalyRule.ALL, limit=10, offset=10),
        clock,
    )

    assert first.matching_ticket_count == second.matching_ticket_count == 129
    assert first.rule_counts == second.rule_counts
    assert first.returned_count == second.returned_count == 10
    assert {ticket.ticket_id for ticket in first.tickets}.isdisjoint(
        ticket.ticket_id for ticket in second.tickets
    )


def test_exact_rule_boundaries_are_not_flagged() -> None:
    reference = datetime.fromisoformat("2024-04-05T00:00:00")
    clock = ReferenceClock(
        mode=ReferenceMode.CUSTOM,
        timestamp=reference,
        dataset_default=reference,
    )
    tickets = (
        _ticket(
            "TKT-EXACT-24",
            created_at=reference - timedelta(hours=24),
            status=TicketStatus.OPEN,
            priority=TicketPriority.HIGH,
        ),
        _ticket(
            "TKT-OVER-24",
            created_at=reference - timedelta(hours=24, seconds=1),
            status=TicketStatus.ESCALATED,
            priority=TicketPriority.CRITICAL,
        ),
        _ticket(
            "TKT-LOW",
            created_at=reference - timedelta(hours=100),
            status=TicketStatus.OPEN,
            priority=TicketPriority.LOW,
        ),
        _ticket(
            "TKT-FUTURE",
            created_at=reference + timedelta(minutes=1),
            status=TicketStatus.OPEN,
            priority=TicketPriority.CRITICAL,
        ),
    )

    result = detect_ticket_anomalies(
        tickets,
        AnomalyQueryRequest(rule=AnomalyRule.OVERDUE_HIGH_PRIORITY),
        clock,
    )

    assert [ticket.ticket_id for ticket in result.tickets] == ["TKT-OVER-24"]
    assert result.tickets[0].unresolved_age_hrs == pytest.approx(24 + 1 / 3600)


def test_constant_duration_baseline_reports_insufficient_variation() -> None:
    reference = datetime.fromisoformat("2024-04-05T00:00:00")
    clock = ReferenceClock(
        mode=ReferenceMode.CUSTOM,
        timestamp=reference,
        dataset_default=reference,
    )
    tickets = tuple(
        _ticket(
            f"TKT-{index}",
            created_at=reference - timedelta(days=2),
            status=TicketStatus.RESOLVED,
            resolution_time_hrs=duration,
            customer_rating=4,
        )
        for index, duration in enumerate((5.0, 5.0, 5.0, 5.0, 5.0), start=1)
    )

    baseline = calculate_iqr_baseline([5.0, 5.0, 5.0, 5.0, 5.0])
    result = detect_ticket_anomalies(
        tickets,
        AnomalyQueryRequest(rule=AnomalyRule.LONG_RESOLUTION),
        clock,
    )

    assert baseline is None
    assert result.tickets == ()
    assert "non-zero variation" in result.warnings[0]


def test_fewer_than_four_durations_reports_insufficient_baseline() -> None:
    reference = datetime.fromisoformat("2024-04-05T00:00:00")
    clock = ReferenceClock(
        mode=ReferenceMode.CUSTOM,
        timestamp=reference,
        dataset_default=reference,
    )
    tickets = tuple(
        _ticket(
            f"TKT-SMALL-{index}",
            created_at=reference - timedelta(days=2),
            status=TicketStatus.RESOLVED,
            resolution_time_hrs=duration,
            customer_rating=4,
        )
        for index, duration in enumerate((1.0, 2.0, 100.0), start=1)
    )

    result = detect_ticket_anomalies(
        tickets,
        AnomalyQueryRequest(rule=AnomalyRule.LONG_RESOLUTION),
        clock,
    )

    assert calculate_iqr_baseline([1.0, 2.0, 100.0]) is None
    assert result.matching_ticket_count == 0
    assert "at least four durations" in result.warnings[0]


def test_empty_resolved_population_has_no_iqr_baseline() -> None:
    reference = datetime.fromisoformat("2024-04-05T00:00:00")
    clock = ReferenceClock(
        mode=ReferenceMode.CUSTOM,
        timestamp=reference,
        dataset_default=reference,
    )
    result = detect_ticket_anomalies(
        (
            _ticket(
                "TKT-OPEN",
                created_at=reference,
                status=TicketStatus.OPEN,
                priority=TicketPriority.LOW,
            ),
        ),
        AnomalyQueryRequest(rule=AnomalyRule.LONG_RESOLUTION),
        clock,
    )

    assert result.long_resolution_baseline is None
    assert result.matching_ticket_count == 0
    assert result.tickets == ()


def test_multiple_anomaly_reasons_are_combined_on_one_ticket() -> None:
    reference = datetime.fromisoformat("2024-04-05T00:00:00")
    clock = ReferenceClock(
        mode=ReferenceMode.CUSTOM,
        timestamp=reference,
        dataset_default=reference,
    )
    durations = (1.0, 2.0, 3.0, 4.0, 100.0)
    tickets = tuple(
        _ticket(
            f"TKT-{index}",
            created_at=reference - timedelta(days=7),
            status=TicketStatus.RESOLVED,
            resolution_time_hrs=duration,
            response_time_hrs=120.0 if duration == 100.0 else 0.5,
            customer_rating=4,
        )
        for index, duration in enumerate(durations, start=1)
    )

    result = detect_ticket_anomalies(
        tickets,
        AnomalyQueryRequest(rule=AnomalyRule.ALL),
        clock,
    )

    flagged = next(ticket for ticket in result.tickets if ticket.ticket_id == "TKT-5")
    assert {flag.rule for flag in flagged.flags} == {
        AnomalyRule.LONG_RESOLUTION,
        AnomalyRule.RESOLUTION_BEFORE_RESPONSE,
    }
    assert result.matching_ticket_count == 1
    assert result.rule_counts.long_resolution == 1
    assert result.rule_counts.resolution_before_response == 1


@pytest.mark.parametrize("values", [[-1.0], [float("nan")], [float("inf")]])
def test_iqr_baseline_rejects_invalid_durations(values: list[float]) -> None:
    with pytest.raises(ValueError, match="finite and nonnegative"):
        calculate_iqr_baseline(values)


def _ticket(
    ticket_id: str,
    *,
    created_at: datetime,
    status: TicketStatus,
    priority: TicketPriority = TicketPriority.HIGH,
    response_time_hrs: float = 0.0,
    resolution_time_hrs: float | None = None,
    customer_rating: int | None = None,
) -> TicketRecord:
    return TicketRecord(
        ticket_id=ticket_id,
        created_at=created_at,
        category=TicketCategory.TECHNICAL,
        priority=priority,
        status=status,
        response_time_hrs=response_time_hrs,
        resolution_time_hrs=resolution_time_hrs,
        agent_id="AGT-01",
        customer_rating=customer_rating,
        issue_summary="Synthetic anomaly boundary test",
    )
