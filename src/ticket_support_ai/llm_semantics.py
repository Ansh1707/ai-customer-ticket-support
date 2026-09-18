"""Compile and verify model plans under explicit user-constraint precedence."""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from ticket_support_ai.capabilities import (
    capability_limitation,
    extract_null_conditions,
    extract_result_limit,
)
from ticket_support_ai.llm_errors import StructuredOutputError
from ticket_support_ai.llm_language import (
    _contains_word,
    _explicit_time_field,
    _extract_explicit_date_range,
    _extract_numeric_conditions,
    _extract_summary_literal,
    _is_negated_value,
    _mask_quoted_literals,
)
from ticket_support_ai.llm_plans import AnalyticsPlan, IntentRoute
from ticket_support_ai.schemas import (
    Aggregation,
    AnalyticsOperation,
    AnalyticsRequest,
    AnomalyQueryRequest,
    ClarificationRequest,
    FilterField,
    GroupField,
    MetricField,
    OutputField,
    QueryIntent,
    QueryRequest,
    RelativePeriod,
    SortDirection,
    SortField,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    TicketTimeField,
)


def _reconcile_interpretation(
    structured: AnalyticsPlan | QueryRequest,
    question: str,
) -> QueryRequest:
    """Apply the single documented semantic-precedence boundary."""

    limitation = capability_limitation(question)
    if limitation is not None:
        return limitation
    if isinstance(structured, AnalyticsPlan):
        request = _compile_analytics_plan(
            _preserve_explicit_constraints(structured, question)
        )
        gaps = _semantic_gaps(question, request)
        if gaps:
            return ClarificationRequest(
                question=(
                    "Please rephrase or simplify the following condition(s): "
                    + "; ".join(gaps)
                    + "."
                ),
                reason=(
                    "The validated model output did not preserve every material "
                    "condition safely, so the query was not executed."
                ),
            )
        return request
    if isinstance(structured, AnomalyQueryRequest):
        request = _preserve_anomaly_request(structured, question)
        gaps = _anomaly_semantic_gaps(question, request)
        if gaps:
            return ClarificationRequest(
                question=(
                    "Please rephrase or simplify the following condition(s): "
                    + "; ".join(gaps)
                    + "."
                ),
                reason=(
                    "The validated model output did not preserve every material "
                    "anomaly condition safely, so the query was not executed."
                ),
            )
        return request
    return structured


def _compile_analytics_plan(plan: AnalyticsPlan) -> AnalyticsRequest:
    """Compile one reconciled model plan to the strict execution contract."""
    filters: list[dict[str, Any]] = []
    _append_set_filter(filters, "category", plan.categories)
    _append_set_filter(filters, "priority", plan.priorities)
    _append_set_filter(filters, "status", plan.statuses)
    _append_exclusion_filters(filters, "category", plan.excluded_categories)
    _append_exclusion_filters(filters, "priority", plan.excluded_priorities)
    _append_exclusion_filters(filters, "status", plan.excluded_statuses)
    _append_set_filter(filters, "ticket_id", plan.ticket_ids)
    _append_set_filter(filters, "agent_id", plan.agent_ids)
    if plan.summary_contains:
        filters.append(
            {
                "field": "issue_summary",
                "operator": "contains",
                "value": plan.summary_contains,
            }
        )
    for condition in plan.numeric_conditions:
        filters.append(
            {
                "field": condition.field,
                "operator": condition.operator,
                "value": condition.value,
            }
        )
    filters.extend(item.model_dump() for item in plan.null_conditions)
    payload: dict[str, Any] = {
        "operation": plan.operation,
        "filters": filters,
    }
    if plan.time_field is not None and plan.relative_period is not None:
        payload["time_filter"] = {
            "field": plan.time_field,
            "relative_period": plan.relative_period,
        }
    elif (
        plan.time_field is not None
        and plan.start_date is not None
        and plan.end_date is not None
    ):
        payload["time_filter"] = {
            "field": plan.time_field,
            "start_date": plan.start_date,
            "end_date": plan.end_date,
        }

    if plan.operation is AnalyticsOperation.LIST:
        payload["selected_fields"] = tuple(OutputField)
        payload["result_limit"] = plan.result_limit
        if plan.sort_field is not None and plan.sort_field is not SortField.RESULT:
            payload["sort"] = [
                {
                    "field": plan.sort_field,
                    "direction": plan.sort_direction or SortDirection.ASCENDING,
                }
            ]
    elif plan.operation is AnalyticsOperation.AGGREGATE:
        payload["aggregation"] = plan.aggregation
        payload["metric"] = plan.metric
    elif plan.operation is AnalyticsOperation.GROUPED_AGGREGATE:
        payload["aggregation"] = plan.aggregation
        payload["group_by"] = plan.group_by
        if plan.aggregation is not Aggregation.COUNT:
            payload["metric"] = plan.metric
        payload["result_limit"] = plan.result_limit
        if plan.sort_field is not None:
            payload["sort"] = [
                {
                    "field": plan.sort_field,
                    "direction": plan.sort_direction or SortDirection.ASCENDING,
                }
            ]

    try:
        return AnalyticsRequest.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(
            "Qwen's analytics plan could not be compiled safely: "
            f"{_validation_summary(exc)}"
        ) from exc


def _append_set_filter(
    filters: list[dict[str, Any]],
    field: str,
    values: tuple[Any, ...],
) -> None:
    if len(values) == 1:
        filters.append({"field": field, "operator": "eq", "value": values[0]})
    elif values:
        filters.append({"field": field, "operator": "in", "values": values})


def _append_exclusion_filters(
    filters: list[dict[str, Any]],
    field: str,
    values: tuple[Any, ...],
) -> None:
    for value in values:
        filters.append({"field": field, "operator": "ne", "value": value})


def _preserve_explicit_constraints(
    plan: AnalyticsPlan,
    question: str,
) -> AnalyticsPlan:
    """Prevent a compact model from dropping literal constraints in the question."""

    lowered = question.casefold()
    instruction_text = _mask_quoted_literals(lowered)
    updates: dict[str, Any] = {}
    explicit_categories = tuple(
        item
        for item in TicketCategory
        if _contains_word(instruction_text, item.value.casefold())
        and not _is_negated_value(instruction_text, item.value.casefold())
    )
    excluded_categories = tuple(
        item
        for item in TicketCategory
        if _is_negated_value(instruction_text, item.value.casefold())
    )
    explicit_priorities = tuple(
        item
        for item in TicketPriority
        if _contains_word(instruction_text, item.value.casefold())
        and not _is_negated_value(instruction_text, item.value.casefold())
    )
    excluded_priorities = tuple(
        item
        for item in TicketPriority
        if _is_negated_value(instruction_text, item.value.casefold())
    )
    # Categorical filters are closed-world dataset values. Rebuild them from the
    # question so a small model cannot silently narrow a result with invented values.
    updates["categories"] = explicit_categories
    updates["excluded_categories"] = excluded_categories
    updates["priorities"] = explicit_priorities
    updates["excluded_priorities"] = excluded_priorities

    unresolved_phrases = (
        "unresolved",
        "awaiting resolution",
        "awaiting a resolution",
        "not yet resolved",
        "still pending",
    )
    if any(phrase in instruction_text for phrase in unresolved_phrases):
        updates["statuses"] = (TicketStatus.OPEN, TicketStatus.ESCALATED)
        updates["excluded_statuses"] = ()
    elif "not resolved within" in instruction_text:
        # This asks about elapsed resolution duration across resolved and unresolved
        # tickets, so it must not be narrowed to status=Resolved.
        updates["statuses"] = ()
        updates["excluded_statuses"] = ()
    else:
        updates["statuses"] = tuple(
            item
            for item in TicketStatus
            if _contains_word(instruction_text, item.value.casefold())
            and not _is_negated_value(instruction_text, item.value.casefold())
        )
        updates["excluded_statuses"] = tuple(
            item
            for item in TicketStatus
            if _is_negated_value(instruction_text, item.value.casefold())
        )

    search_cues = ("summary", "contain", "mention", "search")
    updates["summary_contains"] = (
        _extract_summary_literal(lowered)
        if any(cue in instruction_text for cue in search_cues)
        else None
    )

    period_phrases = {
        "this week": RelativePeriod.THIS_WEEK,
        "last week": RelativePeriod.LAST_WEEK,
        "this month": RelativePeriod.THIS_MONTH,
        "last month": RelativePeriod.LAST_MONTH,
    }
    matched_period = False
    for phrase, period in period_phrases.items():
        if phrase in instruction_text:
            matched_period = True
            updates["relative_period"] = period
            updates["time_field"] = _explicit_time_field(instruction_text)
            break
    temporal_cues = (
        "today",
        "yesterday",
        "between",
        "from ",
        "since",
        "during",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    )
    has_explicit_date = (
        re.search(r"\b\d{4}-\d{2}-\d{2}\b", instruction_text) is not None
    )
    if (
        not matched_period
        and not has_explicit_date
        and not any(cue in instruction_text for cue in temporal_cues)
    ):
        updates.update(
            time_field=None,
            relative_period=None,
            start_date=None,
            end_date=None,
        )
    explicit_range = _extract_explicit_date_range(instruction_text)
    if explicit_range is not None:
        start_date, end_date = explicit_range
        updates.update(
            start_date=start_date,
            end_date=end_date,
            relative_period=None,
            time_field=_explicit_time_field(instruction_text),
        )

    updates["numeric_conditions"] = _extract_numeric_conditions(instruction_text)
    updates["null_conditions"] = extract_null_conditions(instruction_text)

    rating_language = (
        "customer rating" in instruction_text or "satisfaction" in instruction_text
    )
    if "resolution time" in instruction_text:
        updates["metric"] = MetricField.RESOLUTION_TIME_HRS
    elif "response time" in instruction_text:
        updates["metric"] = MetricField.RESPONSE_TIME_HRS
    average_language = "average" in instruction_text or "mean" in instruction_text
    requested_group: GroupField | None = None
    if any(
        phrase in instruction_text
        for phrase in ("which category", "by category", "per category", "each category")
    ):
        requested_group = GroupField.CATEGORY
    elif any(
        phrase in instruction_text
        for phrase in ("which priority", "by priority", "per priority")
    ):
        requested_group = GroupField.PRIORITY
    elif any(
        phrase in instruction_text
        for phrase in ("which status", "by status", "per status")
    ):
        requested_group = GroupField.STATUS
    elif "agent" in instruction_text or "who" in instruction_text:
        requested_group = GroupField.AGENT_ID
    if rating_language:
        updates["metric"] = MetricField.CUSTOMER_RATING
    if average_language:
        updates["aggregation"] = Aggregation.AVERAGE
        updates["operation"] = (
            AnalyticsOperation.GROUPED_AGGREGATE
            if requested_group is not None
            else AnalyticsOperation.AGGREGATE
        )
    if requested_group is not None and any(
        word in instruction_text
        for word in ("most", "highest", "lowest", "worst", "best")
    ):
        updates["operation"] = AnalyticsOperation.GROUPED_AGGREGATE
        updates["group_by"] = requested_group
        updates["sort_field"] = SortField.RESULT
        updates["result_limit"] = 1
    if "resolved the most" in instruction_text:
        updates["aggregation"] = Aggregation.COUNT
        updates["statuses"] = (TicketStatus.RESOLVED,)
    top_match = re.search(r"\b(top|bottom)\s+(\d{1,3})\b", instruction_text)
    if top_match is not None and requested_group is not None:
        updates["operation"] = AnalyticsOperation.GROUPED_AGGREGATE
        updates["aggregation"] = Aggregation.COUNT
        updates["group_by"] = requested_group
        updates["sort_field"] = SortField.RESULT
        updates["sort_direction"] = (
            SortDirection.DESCENDING
            if top_match.group(1) == "top"
            else SortDirection.ASCENDING
        )
        updates["result_limit"] = min(100, max(1, int(top_match.group(2))))
        if "resolved" in instruction_text:
            updates["statuses"] = (TicketStatus.RESOLVED,)
    if requested_group is not None and "count" in instruction_text:
        updates["operation"] = AnalyticsOperation.GROUPED_AGGREGATE
        updates["aggregation"] = Aggregation.COUNT
        updates["group_by"] = requested_group
        if top_match is None and not any(
            word in instruction_text
            for word in ("most", "highest", "lowest", "worst", "best")
        ):
            updates["sort_field"] = SortField(requested_group.value)
            updates["sort_direction"] = SortDirection.ASCENDING
    if any(word in instruction_text for word in ("lowest", "worst")):
        updates["sort_direction"] = SortDirection.ASCENDING
    elif any(word in instruction_text for word in ("most", "highest")):
        updates["sort_direction"] = SortDirection.DESCENDING
    if requested_group is None and (
        "how many" in instruction_text or instruction_text.startswith("count ")
    ):
        updates["operation"] = AnalyticsOperation.COUNT
    if requested_group is None and instruction_text.startswith(("show ", "list ")):
        updates["operation"] = AnalyticsOperation.LIST
    if top_match is None and not any(
        word in instruction_text
        for word in ("most", "highest", "lowest", "worst", "best")
    ):
        updates["result_limit"] = None

    requested_limit = extract_result_limit(instruction_text)
    if requested_limit is not None and 1 <= requested_limit <= 100:
        updates["result_limit"] = requested_limit
    if "oldest" in instruction_text or "newest" in instruction_text:
        updates["sort_field"] = SortField.CREATED_AT
        updates["sort_direction"] = (
            SortDirection.ASCENDING
            if "oldest" in instruction_text
            else SortDirection.DESCENDING
        )
    if "fastest" in instruction_text or "slowest" in instruction_text:
        updates["sort_field"] = SortField.RESULT
        updates["sort_direction"] = (
            SortDirection.ASCENDING
            if "fastest" in instruction_text
            else SortDirection.DESCENDING
        )
    return plan.model_copy(update=updates)


def _preserve_safe_route(route: IntentRoute, question: str) -> IntentRoute:
    """Override high-confidence safety and anomaly cues missed by the small model."""

    lowered = _mask_quoted_literals(question.casefold())
    if re.search(r"\b(predict|forecast|estimate)\b", lowered) and re.search(
        r"\b(future|next|will)\b", lowered
    ):
        return IntentRoute(intent=QueryIntent.UNSUPPORTED)
    if re.search(r"\b(those|these|them|that)\s+tickets?\b", lowered):
        return IntentRoute(intent=QueryIntent.CLARIFICATION)
    anomaly_cues = (
        "anomal",
        "outlier",
        "overdue",
        "resolution times shorter than",
        "resolution time shorter than",
    )
    if any(cue in lowered for cue in anomaly_cues):
        return IntentRoute(intent=QueryIntent.ANOMALIES)
    return route


def _preserve_anomaly_request(
    request: AnomalyQueryRequest,
    question: str,
) -> AnomalyQueryRequest:
    """Preserve explicit anomaly rule and date language from the question."""

    lowered = _mask_quoted_literals(question.casefold())
    updates: dict[str, Any] = {}
    if "overdue" in lowered:
        updates["rule"] = "overdue_high_priority"
    elif "shorter than" in lowered and "response" in lowered:
        updates["rule"] = "resolution_before_response"
    elif ("anomal" in lowered or "outlier" in lowered) and "resolution" in lowered:
        updates["rule"] = "long_resolution"

    period_phrases = {
        "this week": RelativePeriod.THIS_WEEK,
        "last week": RelativePeriod.LAST_WEEK,
        "this month": RelativePeriod.THIS_MONTH,
        "last month": RelativePeriod.LAST_MONTH,
    }
    period = next(
        (value for phrase, value in period_phrases.items() if phrase in lowered),
        None,
    )
    explicit_range = _extract_explicit_date_range(lowered)
    rule = updates.get("rule", request.rule)
    time_field = (
        TicketTimeField.CREATED_AT
        if rule == "overdue_high_priority"
        else _explicit_time_field(lowered, default=TicketTimeField.RESOLVED_AT)
    )
    if explicit_range is not None:
        start_date, end_date = explicit_range
        updates["time_filter"] = {
            "field": time_field,
            "start_date": start_date,
            "end_date": end_date,
        }
    elif period is None:
        updates["time_filter"] = None
    else:
        updates["time_filter"] = {
            "field": time_field,
            "relative_period": period,
        }
    payload = request.model_dump(mode="json")
    payload.update(updates)
    return AnomalyQueryRequest.model_validate(payload)


def _semantic_gaps(question: str, request: AnalyticsRequest) -> tuple[str, ...]:
    """Reject schema-valid requests that lose or invent material user constraints."""

    text = question.casefold()
    instruction_text = _mask_quoted_literals(text)
    gaps: list[str] = []

    def categorical_values(
        field: FilterField,
        *,
        excluded: bool,
    ) -> set[str]:
        values: set[str] = set()
        for item in request.filters:
            if item.field != field:
                continue
            if (excluded and item.operator == "ne") or (
                not excluded and item.operator == "eq"
            ):
                values.add(str(item.value))
            elif not excluded and item.operator == "in":
                values.update(str(value) for value in item.values)
        return values

    for field, values in (
        (FilterField.CATEGORY, TicketCategory),
        (FilterField.PRIORITY, TicketPriority),
    ):
        expected = {
            item.value
            for item in values
            if _contains_word(instruction_text, item.value.casefold())
            and not _is_negated_value(instruction_text, item.value.casefold())
        }
        excluded = {
            item.value
            for item in values
            if _is_negated_value(instruction_text, item.value.casefold())
        }
        if categorical_values(field, excluded=False) != expected:
            gaps.append(f"{field.value} filter")
        if categorical_values(field, excluded=True) != excluded:
            gaps.append(f"negated {field.value} filter")

    unresolved_phrases = (
        "unresolved",
        "awaiting resolution",
        "awaiting a resolution",
        "not yet resolved",
        "still pending",
    )
    if any(phrase in instruction_text for phrase in unresolved_phrases):
        expected_statuses = {TicketStatus.OPEN.value, TicketStatus.ESCALATED.value}
    elif "not resolved within" in instruction_text:
        expected_statuses = set()
    else:
        expected_statuses = {
            item.value
            for item in TicketStatus
            if _contains_word(instruction_text, item.value.casefold())
            and not _is_negated_value(instruction_text, item.value.casefold())
        }
    excluded_statuses = (
        set()
        if "not resolved within" in instruction_text
        else {
            item.value
            for item in TicketStatus
            if _is_negated_value(instruction_text, item.value.casefold())
        }
    )
    if categorical_values(FilterField.STATUS, excluded=False) != expected_statuses:
        gaps.append("status filter")
    if categorical_values(FilterField.STATUS, excluded=True) != excluded_statuses:
        gaps.append("negated status filter")

    summary_cue = re.search(
        r"\b(?:issue\s+)?summar(?:y|ies)\b", instruction_text
    ) and re.search(
        r"\b(?:contain|contains|containing|mention|mentions|search)\b",
        instruction_text,
    )
    expected_summary = _extract_summary_literal(text)
    actual_summaries = [
        item.value
        for item in request.filters
        if item.field == FilterField.ISSUE_SUMMARY and item.operator == "contains"
    ]
    if (summary_cue and expected_summary is None) or (
        expected_summary is not None and actual_summaries != [expected_summary]
    ):
        gaps.append("issue-summary search text")
    elif expected_summary is None and actual_summaries:
        gaps.append("unstated issue-summary filter")

    expected_numeric = {
        (item.field, item.operator, item.value)
        for item in _extract_numeric_conditions(instruction_text)
    }
    actual_numeric = {
        (item.field, item.operator, float(item.value))
        for item in request.filters
        if item.field
        in {
            FilterField.RESPONSE_TIME_HRS,
            FilterField.RESOLUTION_TIME_HRS,
            FilterField.CUSTOMER_RATING,
            FilterField.RESOLUTION_ELAPSED_HRS,
        }
        and item.operator in {"eq", "gt", "gte", "lt", "lte"}
    }
    if actual_numeric != expected_numeric:
        gaps.append("numeric condition")
    if re.search(
        r"\b(?:response time|resolution time|customer rating|satisfaction score|rating)\b"
        r"[^?.!]{0,30}\b(?:between|not equal|different from)\b",
        instruction_text,
    ):
        gaps.append("unsupported numeric comparison")

    periods = {
        "this week": RelativePeriod.THIS_WEEK,
        "last week": RelativePeriod.LAST_WEEK,
        "this month": RelativePeriod.THIS_MONTH,
        "last month": RelativePeriod.LAST_MONTH,
    }
    expected_period = next(
        (period for phrase, period in periods.items() if phrase in instruction_text),
        None,
    )
    expected_range = _extract_explicit_date_range(instruction_text)
    expected_time_field = _explicit_time_field(instruction_text)
    if expected_period is not None:
        if request.time_filter is None or (
            request.time_filter.relative_period != expected_period
            or request.time_filter.field != expected_time_field
        ):
            gaps.append("relative date period")
    elif expected_range is not None:
        if (
            request.time_filter is None
            or (
                request.time_filter.start_date,
                request.time_filter.end_date,
            )
            != expected_range
        ):
            gaps.append("explicit date range")
        elif request.time_filter.field != expected_time_field:
            gaps.append("date field")
    elif (
        re.search(
            r"\b(?:today|yesterday|since|during|january|february|march|april|may|"
            r"june|july|august|september|october|november|december)\b",
            instruction_text,
        )
        and request.time_filter is None
    ):
        gaps.append("date condition")

    top_match = re.search(r"\b(?:top|bottom)\s+(\d{1,3})\b", instruction_text)
    if top_match is not None and request.result_limit != int(top_match.group(1)):
        gaps.append("requested result count")

    expected_null = {
        (item.field, item.operator)
        for item in extract_null_conditions(instruction_text)
    }
    actual_null = {
        (item.field, item.operator)
        for item in request.filters
        if item.operator in {"is_null", "is_not_null"}
    }
    if actual_null != expected_null:
        gaps.append("null condition")
    requested_limit = extract_result_limit(instruction_text)
    if requested_limit is not None and request.result_limit != requested_limit:
        gaps.append("requested result count")
    return tuple(dict.fromkeys(gaps))


def _anomaly_semantic_gaps(
    question: str,
    request: AnomalyQueryRequest,
) -> tuple[str, ...]:
    """Verify material anomaly rule and date cues after deterministic reconciliation."""

    text = _mask_quoted_literals(question.casefold())
    gaps: list[str] = []
    if "overdue" in text:
        expected_rule = "overdue_high_priority"
    elif "shorter than" in text and "response" in text:
        expected_rule = "resolution_before_response"
    elif ("anomal" in text or "outlier" in text) and "resolution" in text:
        expected_rule = "long_resolution"
    else:
        expected_rule = None
    if expected_rule is not None and request.rule != expected_rule:
        gaps.append("anomaly rule")

    periods = {
        "this week": RelativePeriod.THIS_WEEK,
        "last week": RelativePeriod.LAST_WEEK,
        "this month": RelativePeriod.THIS_MONTH,
        "last month": RelativePeriod.LAST_MONTH,
    }
    expected_period = next(
        (period for phrase, period in periods.items() if phrase in text),
        None,
    )
    expected_range = _extract_explicit_date_range(text)
    expected_field = (
        TicketTimeField.CREATED_AT
        if request.rule.value == "overdue_high_priority"
        else _explicit_time_field(text, default=TicketTimeField.RESOLVED_AT)
    )
    if expected_period is not None and (
        request.time_filter is None
        or request.time_filter.relative_period != expected_period
        or request.time_filter.field != expected_field
    ):
        gaps.append("anomaly date period")
    elif expected_range is not None and (
        request.time_filter is None
        or (request.time_filter.start_date, request.time_filter.end_date)
        != expected_range
        or request.time_filter.field != expected_field
    ):
        gaps.append("anomaly date range")
    return tuple(gaps)


def _validation_summary(error: ValidationError) -> str:
    summary = "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'root'}: {item['msg']}"
        for item in error.errors(include_url=False)
    )
    return summary[:1500]
