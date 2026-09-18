"""Natural-language query orchestration and deterministic answer formatting."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Protocol

from ticket_support_ai.analytics import execute_analytics
from ticket_support_ai.anomalies import detect_anomalies
from ticket_support_ai.database import read_tickets
from ticket_support_ai.dates import resolve_reference_clock
from ticket_support_ai.llm import OllamaInterpreter
from ticket_support_ai.schemas import (
    AggregateAnalyticsResult,
    Aggregation,
    AnalyticsRequest,
    AnomalyDetectionResult,
    AnomalyQueryRequest,
    AnomalyRule,
    ClarificationRequest,
    CountAnalyticsResult,
    DateRange,
    FilterField,
    GroupedAnalyticsResult,
    ListAnalyticsResult,
    MetricField,
    NaturalLanguageQueryResult,
    QueryOutcome,
    QueryRequest,
    QueryTiming,
    ReferenceMode,
    SortDirection,
    SortField,
    UnsupportedRequest,
)


class QuestionInterpreter(Protocol):
    """Dependency boundary used by the query service and deterministic tests."""

    async def interpret(self, question: str) -> QueryRequest:
        """Translate a question into one validated request."""


class QueryService:
    """Compose interpretation, reference time, execution, and presentation."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        interpreter: QuestionInterpreter | None = None,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.interpreter = interpreter or OllamaInterpreter()

    async def query(
        self,
        question: str,
        *,
        reference_mode: ReferenceMode | str = ReferenceMode.DATASET,
        custom_reference: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> NaturalLanguageQueryResult:
        """Interpret and answer one question against the current database snapshot."""

        total_started = perf_counter()
        tickets = read_tickets(self.database_path)
        reference_clock = resolve_reference_clock(
            tickets,
            reference_mode,
            custom_reference=custom_reference,
        )
        interpretation_started = perf_counter()
        interpretation = await self.interpreter.interpret(question)
        interpretation_ms = _elapsed_ms(interpretation_started)
        interpretation = _apply_public_paging(interpretation, limit, offset)
        normalized_question = question.strip()
        warnings = tuple(item.message for item in reference_clock.warnings)

        if isinstance(interpretation, ClarificationRequest):
            return NaturalLanguageQueryResult(
                question=normalized_question,
                outcome=QueryOutcome.CLARIFICATION,
                answer=interpretation.question,
                interpretation=interpretation,
                reference_clock=reference_clock,
                warnings=warnings,
                timing=QueryTiming(
                    interpretation_ms=interpretation_ms,
                    execution_ms=0.0,
                    total_ms=_elapsed_ms(total_started),
                ),
            )
        if isinstance(interpretation, UnsupportedRequest):
            return NaturalLanguageQueryResult(
                question=normalized_question,
                outcome=QueryOutcome.UNSUPPORTED,
                answer=f"This request is unsupported: {interpretation.reason}",
                interpretation=interpretation,
                reference_clock=reference_clock,
                warnings=warnings,
                timing=QueryTiming(
                    interpretation_ms=interpretation_ms,
                    execution_ms=0.0,
                    total_ms=_elapsed_ms(total_started),
                ),
            )
        execution_started = perf_counter()
        if isinstance(interpretation, AnalyticsRequest):
            data = execute_analytics(
                self.database_path,
                interpretation,
                reference_clock,
            )
            answer = _format_analytics_answer(data, interpretation)
            if _uses_reference_age(interpretation):
                answer += _reference_suffix(reference_clock.timestamp)
        elif isinstance(interpretation, AnomalyQueryRequest):
            data = detect_anomalies(
                self.database_path,
                interpretation,
                reference_clock,
            )
            answer = _format_anomaly_answer(data)
            if interpretation.rule in {
                AnomalyRule.ALL,
                AnomalyRule.OVERDUE_HIGH_PRIORITY,
            }:
                answer += _reference_suffix(reference_clock.timestamp)
        else:  # pragma: no cover - closed union guard for future schema additions
            raise TypeError(
                f"Unsupported interpretation type: {type(interpretation)!r}"
            )
        execution_ms = _elapsed_ms(execution_started)

        return NaturalLanguageQueryResult(
            question=normalized_question,
            outcome=QueryOutcome.OK,
            answer=answer,
            interpretation=interpretation,
            data=data,
            reference_clock=reference_clock,
            warnings=warnings,
            matching_count=_matching_count(data),
            timing=QueryTiming(
                interpretation_ms=interpretation_ms,
                execution_ms=execution_ms,
                total_ms=_elapsed_ms(total_started),
            ),
        )


def _apply_public_paging(
    interpretation: QueryRequest,
    limit: int,
    offset: int,
) -> QueryRequest:
    """Apply trusted API pagination after validating the model interpretation."""

    if isinstance(interpretation, AnomalyQueryRequest):
        return AnomalyQueryRequest.model_validate(
            {
                **interpretation.model_dump(),
                "limit": limit,
                "offset": offset,
            }
        )
    if isinstance(
        interpretation, AnalyticsRequest
    ) and interpretation.operation.value in {
        "list",
        "grouped_aggregate",
    }:
        return AnalyticsRequest.model_validate(
            {
                **interpretation.model_dump(),
                "limit": limit,
                "offset": offset,
            }
        )
    return interpretation


def _matching_count(data: object) -> int:
    if isinstance(data, CountAnalyticsResult):
        return data.value
    if isinstance(data, AggregateAnalyticsResult):
        return data.matched_row_count
    if isinstance(data, GroupedAnalyticsResult):
        return data.matching_group_count
    if isinstance(data, ListAnalyticsResult):
        return data.matching_count
    if isinstance(data, AnomalyDetectionResult):
        return data.matching_ticket_count
    raise TypeError(f"Unsupported execution result: {type(data)!r}")


def _elapsed_ms(started: float) -> float:
    return max(0.0, (perf_counter() - started) * 1000.0)


def _format_analytics_answer(
    result: (
        ListAnalyticsResult
        | CountAnalyticsResult
        | AggregateAnalyticsResult
        | GroupedAnalyticsResult
    ),
    request: AnalyticsRequest,
) -> str:
    if isinstance(result, CountAnalyticsResult):
        noun = "ticket" if result.value == 1 else "tickets"
        return (
            f"{result.value} {noun} match the interpreted request."
            f"{_range_suffix(result.applied_date_range)}"
        )

    if isinstance(result, AggregateAnalyticsResult):
        metric = _metric_label(result.metric)
        if result.value is None:
            return (
                f"No non-null {metric} values are available across "
                f"{result.matched_row_count} matching tickets."
                f"{_range_suffix(result.applied_date_range)}"
            )
        aggregation = _aggregation_label(result.aggregation)
        return (
            f"The {aggregation} {metric} is {_format_number(result.value)}, calculated "
            f"from {result.contributing_count} values across "
            f"{result.matched_row_count} matching tickets."
            f"{_range_suffix(result.applied_date_range)}"
        )

    if isinstance(result, GroupedAnalyticsResult):
        if not result.rows:
            return (
                "No groups match the interpreted request."
                f"{_range_suffix(result.applied_date_range)}"
            )
        result_ranked = bool(request.sort) and request.sort[0].field is SortField.RESULT
        if result_ranked:
            direction = request.sort[0].direction
            label = "highest" if direction is SortDirection.DESCENDING else "lowest"
            boundary = result.rows[0].value
            leaders = [row.group_value for row in result.rows if row.value == boundary]
            group_label = result.group_by.value.replace("_", " ")
            metric = (
                "ticket count"
                if result.aggregation is Aggregation.COUNT
                else f"{_aggregation_label(result.aggregation)} "
                f"{_metric_label(result.metric)}"
            )
            return (
                f"The {label} {metric} by {group_label} is "
                f"{_format_number(boundary)} for {', '.join(leaders)}."
                f"{_range_suffix(result.applied_date_range)}"
            )
        return (
            f"Returned {result.returned_count} of {result.matching_group_count} "
            f"matching groups.{_range_suffix(result.applied_date_range)}"
        )

    if result.matching_count == 0:
        return (
            "No tickets match the interpreted request."
            f"{_range_suffix(result.applied_date_range)}"
        )
    if result.truncated:
        return (
            f"Found {result.matching_count} matching tickets and returned "
            f"{result.returned_count} from offset {result.offset}."
            f"{_range_suffix(result.applied_date_range)}"
        )
    noun = "ticket" if result.matching_count == 1 else "tickets"
    return (
        f"Found and returned {result.matching_count} matching {noun}."
        f"{_range_suffix(result.applied_date_range)}"
    )


def _format_anomaly_answer(result: AnomalyDetectionResult) -> str:
    if result.matching_ticket_count == 0:
        return (
            "No anomalous tickets were found."
            f"{_range_suffix(result.applied_date_range)}"
        )
    noun = "ticket" if result.matching_ticket_count == 1 else "tickets"
    components = []
    if result.rule_counts.long_resolution:
        components.append(f"{result.rule_counts.long_resolution} long-resolution")
    if result.rule_counts.overdue_high_priority:
        components.append(
            f"{result.rule_counts.overdue_high_priority} overdue high-priority"
        )
    if result.rule_counts.resolution_before_response:
        components.append(
            f"{result.rule_counts.resolution_before_response} timing-inconsistency"
        )
    breakdown = ", ".join(components)
    detail = f" ({breakdown})" if breakdown else ""
    page = (
        f" Returning {result.returned_count} from offset {result.offset}."
        if result.truncated
        else ""
    )
    return (
        f"Found {result.matching_ticket_count} anomalous {noun}{detail}.{page}"
        f"{_range_suffix(result.applied_date_range)}"
    )


def _range_suffix(date_range: DateRange | None) -> str:
    if date_range is None:
        return ""
    start = date_range.start.isoformat(sep=" ", timespec="minutes")
    end = date_range.end.isoformat(sep=" ", timespec="minutes")
    return f" Applied range: {start} to {end} (end excluded; {date_range.label})."


def _reference_suffix(reference: datetime) -> str:
    value = reference.isoformat(sep=" ", timespec="minutes")
    return f" Reference time: {value} dataset-local."


def _uses_reference_age(request: AnalyticsRequest) -> bool:
    return any(
        getattr(item, "field", None) is FilterField.RESOLUTION_ELAPSED_HRS
        for item in request.filters
    )


def _aggregation_label(aggregation: Aggregation) -> str:
    return {
        Aggregation.AVERAGE: "average",
        Aggregation.MINIMUM: "minimum",
        Aggregation.MAXIMUM: "maximum",
        Aggregation.SUM: "sum of",
        Aggregation.COUNT: "count of",
    }[aggregation]


def _metric_label(metric: MetricField | None) -> str:
    if metric is None:
        return "value"
    return {
        MetricField.RESPONSE_TIME_HRS: "response time in hours",
        MetricField.RESOLUTION_TIME_HRS: "resolution time in hours",
        MetricField.CUSTOMER_RATING: "customer rating",
    }[metric]


def _format_number(value: float | None) -> str:
    if value is None:
        return "null"
    if isinstance(value, int) or value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")
