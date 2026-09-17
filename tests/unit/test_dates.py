"""Tests for shared dataset-local date and reference-clock semantics."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ticket_support_ai.dates import (
    HISTORICAL_STATUS_LIMITATION,
    DateInterpretationError,
    dataset_reference_time,
    explicit_date_range,
    explicit_datetime_range,
    inferred_resolution_at,
    latest_event_time,
    relative_period_range,
    resolve_reference_clock,
    ticket_time,
    tickets_in_range,
    unresolved_age_hours,
)
from ticket_support_ai.ingestion import validate_csv
from ticket_support_ai.schemas import (
    ReferenceMode,
    RelativePeriod,
    TicketCategory,
    TicketPriority,
    TicketRecord,
    TicketStatus,
    TicketTimeField,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_TICKETS = validate_csv(PROJECT_ROOT / "support_tickets.csv").tickets


def ticket(
    *,
    ticket_id: str = "TKT-TEST",
    created_at: datetime = datetime(2024, 4, 4, 0, 0),  # noqa: DTZ001
    status: TicketStatus = TicketStatus.OPEN,
    resolution_time_hrs: float | None = None,
    customer_rating: int | None = None,
) -> TicketRecord:
    return TicketRecord(
        ticket_id=ticket_id,
        created_at=created_at,
        category=TicketCategory.TECHNICAL,
        priority=TicketPriority.HIGH,
        status=status,
        response_time_hrs=1.0,
        resolution_time_hrs=resolution_time_hrs,
        agent_id="AGT-01",
        customer_rating=customer_rating,
        issue_summary="Test ticket",
    )


def test_dataset_reference_uses_latest_creation_or_inferred_resolution() -> None:
    assert latest_event_time(SOURCE_TICKETS) == datetime(2024, 4, 4, 12, 23)  # noqa: DTZ001
    assert dataset_reference_time(SOURCE_TICKETS) == datetime(2024, 4, 5, 0, 0)  # noqa: DTZ001


def test_dataset_reference_clock_has_no_warning() -> None:
    clock = resolve_reference_clock(SOURCE_TICKETS)

    assert clock.mode is ReferenceMode.DATASET
    assert clock.timestamp == datetime(2024, 4, 5, 0, 0)  # noqa: DTZ001
    assert clock.dataset_default == clock.timestamp
    assert clock.warnings == ()


def test_current_and_custom_reference_modes() -> None:
    current = datetime(2026, 9, 17, 12, 0)  # noqa: DTZ001
    custom = datetime(2024, 3, 15, 8, 30)  # noqa: DTZ001

    current_clock = resolve_reference_clock(
        SOURCE_TICKETS,
        ReferenceMode.CURRENT,
        current_time=current,
    )
    custom_clock = resolve_reference_clock(
        SOURCE_TICKETS,
        ReferenceMode.CUSTOM,
        custom_reference=custom,
    )

    assert current_clock.timestamp == current
    assert current_clock.warnings == ()
    assert custom_clock.timestamp == custom
    assert [warning.code for warning in custom_clock.warnings] == [
        "reference_precedes_dataset_events"
    ]


@pytest.mark.parametrize(
    ("period", "expected_start", "expected_end"),
    [
        (
            RelativePeriod.THIS_WEEK,
            datetime(2024, 4, 1, 0, 0),  # noqa: DTZ001
            datetime(2024, 4, 5, 0, 0),  # noqa: DTZ001
        ),
        (
            RelativePeriod.LAST_WEEK,
            datetime(2024, 3, 25, 0, 0),  # noqa: DTZ001
            datetime(2024, 4, 1, 0, 0),  # noqa: DTZ001
        ),
        (
            RelativePeriod.THIS_MONTH,
            datetime(2024, 4, 1, 0, 0),  # noqa: DTZ001
            datetime(2024, 4, 5, 0, 0),  # noqa: DTZ001
        ),
        (
            RelativePeriod.LAST_MONTH,
            datetime(2024, 3, 1, 0, 0),  # noqa: DTZ001
            datetime(2024, 4, 1, 0, 0),  # noqa: DTZ001
        ),
    ],
)
def test_relative_calendar_ranges(
    period: RelativePeriod,
    expected_start: datetime,
    expected_end: datetime,
) -> None:
    reference = datetime(2024, 4, 5, 0, 0)  # noqa: DTZ001

    result = relative_period_range(period, reference)

    assert result.start == expected_start
    assert result.end == expected_end


def test_this_period_can_be_empty_at_exact_calendar_boundary() -> None:
    reference = datetime(2024, 4, 1, 0, 0)  # noqa: DTZ001

    this_week = relative_period_range(RelativePeriod.THIS_WEEK, reference)
    this_month = relative_period_range(RelativePeriod.THIS_MONTH, reference)

    assert this_week.start == this_week.end == reference
    assert this_month.start == this_month.end == reference


def test_explicit_whole_day_range_has_inclusive_end_date() -> None:
    result = explicit_date_range(date(2024, 3, 1), date(2024, 3, 10))

    assert result.start == datetime(2024, 3, 1, 0, 0)  # noqa: DTZ001
    assert result.end == datetime(2024, 3, 11, 0, 0)  # noqa: DTZ001
    assert result.contains(datetime(2024, 3, 10, 23, 59))  # noqa: DTZ001
    assert not result.contains(result.end)


def test_explicit_timestamp_range_is_half_open() -> None:
    start = datetime(2024, 3, 1, 12, 0)  # noqa: DTZ001
    end = datetime(2024, 3, 2, 12, 0)  # noqa: DTZ001
    result = explicit_datetime_range(start, end)

    assert result.contains(start)
    assert not result.contains(end)


def test_inferred_resolution_and_time_field_selection() -> None:
    resolved = ticket(
        status=TicketStatus.RESOLVED,
        resolution_time_hrs=12.5,
        customer_rating=4,
    )
    unresolved = ticket(ticket_id="TKT-OPEN")

    assert inferred_resolution_at(resolved) == datetime(2024, 4, 4, 12, 30)  # noqa: DTZ001
    assert ticket_time(resolved, TicketTimeField.CREATED_AT) == resolved.created_at
    assert ticket_time(resolved, TicketTimeField.RESOLVED_AT) == inferred_resolution_at(
        resolved
    )
    assert ticket_time(unresolved, TicketTimeField.RESOLVED_AT) is None


def test_ticket_filter_uses_half_open_boundaries_and_selected_field() -> None:
    start = datetime(2024, 4, 4, 0, 0)  # noqa: DTZ001
    end = datetime(2024, 4, 5, 0, 0)  # noqa: DTZ001
    date_range = explicit_datetime_range(start, end)
    created_at_start = ticket(ticket_id="TKT-START", created_at=start)
    created_at_end = ticket(ticket_id="TKT-END", created_at=end)
    resolved_inside = ticket(
        ticket_id="TKT-RESOLVED",
        created_at=datetime(2024, 4, 3, 20, 0),  # noqa: DTZ001
        status=TicketStatus.RESOLVED,
        resolution_time_hrs=8.0,
        customer_rating=5,
    )

    by_creation = tickets_in_range(
        (created_at_start, created_at_end, resolved_inside),
        date_range,
        TicketTimeField.CREATED_AT,
    )
    by_resolution = tickets_in_range(
        (created_at_start, created_at_end, resolved_inside),
        date_range,
        TicketTimeField.RESOLVED_AT,
    )

    assert [item.ticket_id for item in by_creation] == ["TKT-START"]
    assert [item.ticket_id for item in by_resolution] == ["TKT-RESOLVED"]


def test_unresolved_age_excludes_resolved_and_future_created_tickets() -> None:
    reference = datetime(2024, 4, 5, 0, 0)  # noqa: DTZ001
    unresolved = ticket()
    at_reference = ticket(ticket_id="TKT-NOW", created_at=reference)
    future = ticket(
        ticket_id="TKT-FUTURE",
        created_at=datetime(2024, 4, 5, 0, 1),  # noqa: DTZ001
    )
    resolved = ticket(
        ticket_id="TKT-RESOLVED",
        status=TicketStatus.RESOLVED,
        resolution_time_hrs=2.0,
        customer_rating=5,
    )

    assert unresolved_age_hours(unresolved, reference) == 24.0
    assert unresolved_age_hours(at_reference, reference) == 0.0
    assert unresolved_age_hours(future, reference) is None
    assert unresolved_age_hours(resolved, reference) is None


@pytest.mark.parametrize(
    "operation",
    [
        lambda: resolve_reference_clock((), ReferenceMode.DATASET),
        lambda: resolve_reference_clock(SOURCE_TICKETS, ReferenceMode.CUSTOM),
        lambda: resolve_reference_clock(
            SOURCE_TICKETS,
            ReferenceMode.CUSTOM,
            custom_reference=datetime(2024, 4, 5, tzinfo=UTC),
        ),
        lambda: explicit_date_range(date(2024, 3, 2), date(2024, 3, 1)),
        lambda: explicit_datetime_range(
            datetime(2024, 3, 2, 0, 0),  # noqa: DTZ001
            datetime(2024, 3, 1, 0, 0),  # noqa: DTZ001
        ),
        lambda: relative_period_range("next_week", datetime(2024, 4, 5)),  # noqa: DTZ001
    ],
)
def test_invalid_date_requests_are_rejected(operation) -> None:
    with pytest.raises(DateInterpretationError):
        operation()


def test_historical_status_limitation_is_explicit() -> None:
    assert "cannot reconstruct" in HISTORICAL_STATUS_LIMITATION
