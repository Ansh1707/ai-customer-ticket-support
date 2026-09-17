"""Shared reference-clock, calendar-range, and ticket-age semantics."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta

from ticket_support_ai.schemas import (
    DateRange,
    DateWarning,
    ReferenceClock,
    ReferenceMode,
    RelativePeriod,
    TicketRecord,
    TicketStatus,
    TicketTimeField,
)

HISTORICAL_STATUS_LIMITATION = (
    "The dataset contains only the supplied current-status snapshot, so it cannot "
    "reconstruct what a ticket's status was at an earlier date."
)


class DateInterpretationError(ValueError):
    """Raised when a requested reference clock or date range is invalid."""


def inferred_resolution_at(ticket: TicketRecord) -> datetime | None:
    """Return creation plus recorded resolution hours for a resolved ticket."""

    if (
        ticket.status is not TicketStatus.RESOLVED
        or ticket.resolution_time_hrs is None
    ):
        return None
    return ticket.created_at + timedelta(hours=ticket.resolution_time_hrs)


def latest_event_time(tickets: Iterable[TicketRecord]) -> datetime | None:
    """Return the latest creation or inferred resolution timestamp."""

    latest: datetime | None = None
    for ticket in tickets:
        candidates = (ticket.created_at, inferred_resolution_at(ticket))
        for candidate in candidates:
            if candidate is not None and (latest is None or candidate > latest):
                latest = candidate
    return latest


def dataset_reference_time(tickets: Iterable[TicketRecord]) -> datetime:
    """Return midnight immediately after the date of the latest dataset event."""

    latest = latest_event_time(tickets)
    if latest is None:
        raise DateInterpretationError(
            "Cannot derive a dataset reference time from an empty ticket collection."
        )
    return datetime.combine(latest.date() + timedelta(days=1), time.min)


def current_local_time() -> datetime:
    """Return the computer's current local wall-clock time without timezone metadata."""

    return datetime.now(UTC).astimezone().replace(tzinfo=None, microsecond=0)


def resolve_reference_clock(
    tickets: Iterable[TicketRecord],
    mode: ReferenceMode | str = ReferenceMode.DATASET,
    *,
    custom_reference: datetime | None = None,
    current_time: datetime | None = None,
) -> ReferenceClock:
    """Resolve the selected clock and warn when it predates dataset events."""

    ticket_list = tuple(tickets)
    try:
        selected_mode = ReferenceMode(mode)
    except ValueError as exc:
        raise DateInterpretationError(f"Unsupported reference mode: {mode!r}.") from exc

    latest = latest_event_time(ticket_list)
    dataset_default = (
        dataset_reference_time(ticket_list) if latest is not None else None
    )

    if selected_mode is ReferenceMode.DATASET:
        if custom_reference is not None or current_time is not None:
            raise DateInterpretationError(
                "Dataset reference mode does not accept a custom or current timestamp."
            )
        if dataset_default is None:
            raise DateInterpretationError(
                "Cannot use dataset reference mode without any tickets."
            )
        timestamp = dataset_default
    elif selected_mode is ReferenceMode.CURRENT:
        if custom_reference is not None:
            raise DateInterpretationError(
                "Current reference mode does not accept a custom timestamp."
            )
        timestamp = current_time if current_time is not None else current_local_time()
    else:
        if current_time is not None:
            raise DateInterpretationError(
                "Custom reference mode does not accept a current timestamp override."
            )
        if custom_reference is None:
            raise DateInterpretationError(
                "Custom reference mode requires a custom timestamp."
            )
        timestamp = custom_reference

    _require_dataset_local(timestamp, "Reference timestamp")
    warnings: list[DateWarning] = []
    if latest is not None and timestamp < latest:
        warnings.append(
            DateWarning(
                code="reference_precedes_dataset_events",
                message=(
                    "The selected reference precedes one or more recorded dataset "
                    "events. Future-created tickets are excluded from age calculations, "
                    "but historical status cannot be reconstructed from this snapshot."
                ),
            )
        )

    return ReferenceClock(
        mode=selected_mode,
        timestamp=timestamp,
        dataset_default=dataset_default,
        warnings=tuple(warnings),
    )


def relative_period_range(
    period: RelativePeriod | str,
    reference: datetime,
) -> DateRange:
    """Build a half-open week or month range relative to the reference time."""

    _require_dataset_local(reference, "Reference timestamp")
    try:
        selected_period = RelativePeriod(period)
    except ValueError as exc:
        raise DateInterpretationError(f"Unsupported relative period: {period!r}.") from exc

    day_start = datetime.combine(reference.date(), time.min)
    week_start = day_start - timedelta(days=reference.weekday())
    month_start = day_start.replace(day=1)

    if selected_period is RelativePeriod.THIS_WEEK:
        start, end, label = week_start, reference, "this week"
    elif selected_period is RelativePeriod.LAST_WEEK:
        start, end, label = (
            week_start - timedelta(days=7),
            week_start,
            "last week",
        )
    elif selected_period is RelativePeriod.THIS_MONTH:
        start, end, label = month_start, reference, "this month"
    else:
        end = month_start
        previous_month_last_day = month_start.date() - timedelta(days=1)
        start = datetime.combine(previous_month_last_day.replace(day=1), time.min)
        label = "last month"

    return DateRange(start=start, end=end, label=label)


def explicit_date_range(start: date, end_inclusive: date) -> DateRange:
    """Build a whole-day range with an inclusive user-facing end date."""

    if end_inclusive < start:
        raise DateInterpretationError(
            "Explicit end date cannot be earlier than the start date."
        )
    return DateRange(
        start=datetime.combine(start, time.min),
        end=datetime.combine(end_inclusive + timedelta(days=1), time.min),
        label=f"{start.isoformat()} through {end_inclusive.isoformat()}",
    )


def explicit_datetime_range(start: datetime, end_exclusive: datetime) -> DateRange:
    """Build an explicit half-open timestamp range."""

    _require_dataset_local(start, "Range start")
    _require_dataset_local(end_exclusive, "Range end")
    if end_exclusive <= start:
        raise DateInterpretationError(
            "Explicit timestamp range end must be later than its start."
        )
    return DateRange(
        start=start,
        end=end_exclusive,
        label=f"{start.isoformat()} through {end_exclusive.isoformat()} (end excluded)",
    )


def ticket_time(
    ticket: TicketRecord,
    field: TicketTimeField | str,
) -> datetime | None:
    """Return the selected creation or inferred-resolution timestamp."""

    try:
        selected_field = TicketTimeField(field)
    except ValueError as exc:
        raise DateInterpretationError(f"Unsupported ticket time field: {field!r}.") from exc
    if selected_field is TicketTimeField.CREATED_AT:
        return ticket.created_at
    return inferred_resolution_at(ticket)


def tickets_in_range(
    tickets: Iterable[TicketRecord],
    date_range: DateRange,
    field: TicketTimeField | str,
) -> tuple[TicketRecord, ...]:
    """Filter tickets using one shared half-open range implementation."""

    matching: list[TicketRecord] = []
    for ticket in tickets:
        timestamp = ticket_time(ticket, field)
        if timestamp is not None and date_range.contains(timestamp):
            matching.append(ticket)
    return tuple(matching)


def unresolved_age_hours(
    ticket: TicketRecord,
    reference: datetime,
) -> float | None:
    """Return unresolved age, excluding resolved or future-created tickets."""

    _require_dataset_local(reference, "Reference timestamp")
    if ticket.status is TicketStatus.RESOLVED or ticket.created_at > reference:
        return None
    return (reference - ticket.created_at).total_seconds() / 3600


def _require_dataset_local(value: datetime, label: str) -> None:
    if value.tzinfo is not None:
        raise DateInterpretationError(
            f"{label} must not contain timezone information because the source "
            "dataset does not define a timezone."
        )
