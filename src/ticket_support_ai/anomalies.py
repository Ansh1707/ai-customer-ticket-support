"""Deterministic, explainable anomaly detection over the ticket snapshot."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from pathlib import Path

from ticket_support_ai.database import read_tickets
from ticket_support_ai.dates import (
    explicit_date_range,
    inferred_resolution_at,
    relative_period_range,
    ticket_time,
    unresolved_age_hours,
)
from ticket_support_ai.schemas import (
    AnomalyDetectionResult,
    AnomalyFlag,
    AnomalyQueryRequest,
    AnomalyRule,
    AnomalyRuleCounts,
    AnomalyTicket,
    DateRange,
    LongResolutionBaseline,
    ReferenceClock,
    TicketRecord,
    TicketStatus,
)

IQR_MULTIPLIER = 1.5
OVERDUE_HIGH_PRIORITY_HOURS = 24.0
_HIGH_PRIORITIES = {"High", "Critical"}


def detect_anomalies(
    database_path: str | Path,
    request: AnomalyQueryRequest,
    reference_clock: ReferenceClock,
) -> AnomalyDetectionResult:
    """Load the snapshot read-only and execute the requested anomaly rules."""

    tickets = read_tickets(database_path)
    return detect_ticket_anomalies(tickets, request, reference_clock)


def detect_ticket_anomalies(
    tickets: Iterable[TicketRecord],
    request: AnomalyQueryRequest,
    reference_clock: ReferenceClock,
) -> AnomalyDetectionResult:
    """Apply anomaly rules to typed tickets and return unique, paginated findings."""

    ticket_list = tuple(tickets)
    applied_range = _resolve_date_range(request, reference_clock)
    include_long = request.rule in {AnomalyRule.ALL, AnomalyRule.LONG_RESOLUTION}
    include_overdue = request.rule in {
        AnomalyRule.ALL,
        AnomalyRule.OVERDUE_HIGH_PRIORITY,
    }
    include_data_quality = request.rule in {
        AnomalyRule.ALL,
        AnomalyRule.RESOLUTION_BEFORE_RESPONSE,
    }
    baseline = (
        calculate_iqr_baseline(
            ticket.resolution_time_hrs
            for ticket in ticket_list
            if ticket.status is TicketStatus.RESOLVED
            and ticket.resolution_time_hrs is not None
        )
        if include_long
        else None
    )

    findings: list[AnomalyTicket] = []
    long_count = 0
    overdue_count = 0
    data_quality_count = 0
    for ticket in ticket_list:
        if not _inside_requested_range(ticket, request, applied_range):
            continue

        flags: list[AnomalyFlag] = []
        if include_long and baseline is not None:
            long_flag = _long_resolution_flag(ticket, baseline)
            if long_flag is not None:
                flags.append(long_flag)
                long_count += 1

        age = unresolved_age_hours(ticket, reference_clock.timestamp)
        if include_overdue:
            overdue_flag = _overdue_high_priority_flag(ticket, age)
            if overdue_flag is not None:
                flags.append(overdue_flag)
                overdue_count += 1

        if include_data_quality:
            data_quality_flag = _resolution_before_response_flag(ticket)
            if data_quality_flag is not None:
                flags.append(data_quality_flag)
                data_quality_count += 1

        if flags:
            findings.append(
                AnomalyTicket(
                    ticket_id=ticket.ticket_id,
                    created_at=ticket.created_at,
                    category=ticket.category,
                    priority=ticket.priority,
                    status=ticket.status,
                    agent_id=ticket.agent_id,
                    issue_summary=ticket.issue_summary,
                    response_time_hrs=ticket.response_time_hrs,
                    resolution_time_hrs=ticket.resolution_time_hrs,
                    unresolved_age_hrs=age,
                    flags=tuple(flags),
                )
            )

    findings.sort(key=_anomaly_sort_key)
    page = findings[request.offset : request.offset + request.limit]
    return AnomalyDetectionResult(
        requested_rule=request.rule,
        tickets=tuple(page),
        matching_ticket_count=len(findings),
        returned_count=len(page),
        rule_counts=AnomalyRuleCounts(
            long_resolution=long_count,
            overdue_high_priority=overdue_count,
            resolution_before_response=data_quality_count,
        ),
        long_resolution_baseline=baseline,
        overdue_threshold_hrs=OVERDUE_HIGH_PRIORITY_HOURS,
        offset=request.offset,
        limit=request.limit,
        truncated=request.offset + len(page) < len(findings),
        reference_clock=reference_clock,
        applied_date_range=applied_range,
        warnings=(
            (
                "The long-resolution IQR rule needs at least four durations with "
                "non-zero variation; no long-resolution flags were calculated."
            ),
        )
        if include_long and baseline is None
        else (),
    )


def calculate_iqr_baseline(
    values: Iterable[float],
) -> LongResolutionBaseline | None:
    """Calculate a Tukey upper fence using linearly interpolated type-7 quartiles."""

    ordered = sorted(float(value) for value in values)
    if any(not math.isfinite(value) or value < 0 for value in ordered):
        raise ValueError("Resolution durations must be finite and nonnegative.")
    if len(ordered) < 4:
        return None

    q1 = _linear_percentile(ordered, 0.25)
    q3 = _linear_percentile(ordered, 0.75)
    iqr = q3 - q1
    if iqr == 0:
        return None
    return LongResolutionBaseline(
        sample_size=len(ordered),
        q1_hrs=q1,
        q3_hrs=q3,
        iqr_hrs=iqr,
        multiplier=IQR_MULTIPLIER,
        upper_fence_hrs=q3 + IQR_MULTIPLIER * iqr,
    )


def _linear_percentile(ordered: Sequence[float], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] + (
        ordered[upper_index] - ordered[lower_index]
    ) * fraction


def _long_resolution_flag(
    ticket: TicketRecord,
    baseline: LongResolutionBaseline,
) -> AnomalyFlag | None:
    duration = ticket.resolution_time_hrs
    if ticket.status is not TicketStatus.RESOLVED or duration is None:
        return None
    if duration <= baseline.upper_fence_hrs:
        return None
    resolved_at = inferred_resolution_at(ticket)
    if resolved_at is None:
        return None
    return AnomalyFlag(
        rule=AnomalyRule.LONG_RESOLUTION,
        observed_value_hrs=duration,
        threshold_hrs=baseline.upper_fence_hrs,
        event_at=resolved_at,
        reason=(
            f"Resolution took {duration:.2f} hours, exceeding the "
            f"{baseline.upper_fence_hrs:.2f}-hour 1.5×IQR upper fence."
        ),
    )


def _overdue_high_priority_flag(
    ticket: TicketRecord,
    age: float | None,
) -> AnomalyFlag | None:
    if (
        ticket.status is TicketStatus.RESOLVED
        or ticket.priority.value not in _HIGH_PRIORITIES
        or age is None
        or age <= OVERDUE_HIGH_PRIORITY_HOURS
    ):
        return None
    return AnomalyFlag(
        rule=AnomalyRule.OVERDUE_HIGH_PRIORITY,
        observed_value_hrs=age,
        threshold_hrs=OVERDUE_HIGH_PRIORITY_HOURS,
        event_at=ticket.created_at,
        reason=(
            f"{ticket.priority.value} priority ticket is still {ticket.status.value} "
            f"after {age:.2f} hours, exceeding the 24-hour threshold."
        ),
    )


def _resolution_before_response_flag(ticket: TicketRecord) -> AnomalyFlag | None:
    resolution = ticket.resolution_time_hrs
    response = ticket.response_time_hrs
    if resolution is None or resolution >= response:
        return None
    event_at = inferred_resolution_at(ticket) or ticket.created_at
    return AnomalyFlag(
        rule=AnomalyRule.RESOLUTION_BEFORE_RESPONSE,
        observed_value_hrs=response,
        threshold_hrs=resolution,
        event_at=event_at,
        reason=(
            f"Reported resolution time ({resolution:.2f} hours) is shorter than "
            f"first-response time ({response:.2f} hours). Values are preserved "
            "as an observed source-data inconsistency."
        ),
    )


def _resolve_date_range(
    request: AnomalyQueryRequest,
    reference_clock: ReferenceClock,
) -> DateRange | None:
    time_filter = request.time_filter
    if time_filter is None:
        return None
    if time_filter.relative_period is not None:
        return relative_period_range(
            time_filter.relative_period,
            reference_clock.timestamp,
        )
    if time_filter.start_date is None or time_filter.end_date is None:
        raise ValueError("Validated explicit time filter is missing a date boundary.")
    return explicit_date_range(time_filter.start_date, time_filter.end_date)


def _inside_requested_range(
    ticket: TicketRecord,
    request: AnomalyQueryRequest,
    applied_range: DateRange | None,
) -> bool:
    if applied_range is None or request.time_filter is None:
        return True
    value = ticket_time(ticket, request.time_filter.field)
    return value is not None and applied_range.contains(value)


def _anomaly_sort_key(ticket: AnomalyTicket) -> tuple[float, str]:
    severity = max(
        flag.observed_value_hrs / flag.threshold_hrs
        if flag.threshold_hrs > 0
        else flag.observed_value_hrs
        for flag in ticket.flags
    )
    return -severity, ticket.ticket_id
