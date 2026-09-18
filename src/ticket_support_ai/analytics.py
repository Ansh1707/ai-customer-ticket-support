"""Parameterized read-only execution for validated analytics requests."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ticket_support_ai.database import database_connection
from ticket_support_ai.dates import explicit_date_range, relative_period_range
from ticket_support_ai.schemas import (
    AggregateAnalyticsResult,
    Aggregation,
    AnalyticsExecutionResult,
    AnalyticsOperation,
    AnalyticsRequest,
    CountAnalyticsResult,
    DateRange,
    EqualityFilter,
    FilterField,
    GroupedAnalyticsResult,
    GroupedResultRow,
    GroupField,
    ListAnalyticsResult,
    MembershipFilter,
    NullFilter,
    NumericComparisonFilter,
    OutputField,
    ReferenceClock,
    SortDirection,
    SortField,
    SummaryContainsFilter,
    TicketResultRow,
    TicketTimeField,
)

_RESOLVED_AT_SQL = "datetime(t.created_at, '+' || t.resolution_time_hrs || ' hours')"
_UNRESOLVED_AGE_SQL = """
CASE
    WHEN t.status IN ('Open', 'Escalated')
         AND datetime(t.created_at) <= datetime(:reference_time)
    THEN (julianday(:reference_time) - julianday(t.created_at)) * 24.0
    ELSE NULL
END
""".strip()
_RESOLUTION_ELAPSED_SQL = """
CASE
    WHEN t.status = 'Resolved' THEN t.resolution_time_hrs
    WHEN t.status IN ('Open', 'Escalated')
         AND datetime(t.created_at) <= datetime(:reference_time)
    THEN (julianday(:reference_time) - julianday(t.created_at)) * 24.0
    ELSE NULL
END
""".strip()

_FILTER_SQL = {
    FilterField.TICKET_ID: "t.ticket_id",
    FilterField.CATEGORY: "t.category",
    FilterField.PRIORITY: "t.priority",
    FilterField.STATUS: "t.status",
    FilterField.RESPONSE_TIME_HRS: "t.response_time_hrs",
    FilterField.RESOLUTION_TIME_HRS: "t.resolution_time_hrs",
    FilterField.AGENT_ID: "t.agent_id",
    FilterField.CUSTOMER_RATING: "t.customer_rating",
    FilterField.ISSUE_SUMMARY: "t.issue_summary",
    FilterField.RESOLUTION_ELAPSED_HRS: _RESOLUTION_ELAPSED_SQL,
}

_OUTPUT_SQL = {
    OutputField.TICKET_ID: "t.ticket_id",
    OutputField.CREATED_AT: "t.created_at",
    OutputField.CATEGORY: "t.category",
    OutputField.PRIORITY: "t.priority",
    OutputField.STATUS: "t.status",
    OutputField.RESPONSE_TIME_HRS: "t.response_time_hrs",
    OutputField.RESOLUTION_TIME_HRS: "t.resolution_time_hrs",
    OutputField.RESOLVED_AT: _RESOLVED_AT_SQL,
    OutputField.AGENT_ID: "t.agent_id",
    OutputField.CUSTOMER_RATING: "t.customer_rating",
    OutputField.ISSUE_SUMMARY: "t.issue_summary",
    OutputField.UNRESOLVED_AGE_HRS: _UNRESOLVED_AGE_SQL,
    OutputField.RESOLUTION_ELAPSED_HRS: _RESOLUTION_ELAPSED_SQL,
}

_METRIC_SQL = {
    "response_time_hrs": "t.response_time_hrs",
    "resolution_time_hrs": "t.resolution_time_hrs",
    "customer_rating": "t.customer_rating",
}

_GROUP_SQL = {
    GroupField.AGENT_ID: "t.agent_id",
    GroupField.CATEGORY: "t.category",
    GroupField.PRIORITY: "t.priority",
    GroupField.STATUS: "t.status",
}

_SORT_SQL = {
    SortField.TICKET_ID: "t.ticket_id",
    SortField.CREATED_AT: "t.created_at",
    SortField.CATEGORY: "t.category",
    SortField.PRIORITY: "t.priority",
    SortField.STATUS: "t.status",
    SortField.RESPONSE_TIME_HRS: "t.response_time_hrs",
    SortField.RESOLUTION_TIME_HRS: "t.resolution_time_hrs",
    SortField.RESOLVED_AT: _RESOLVED_AT_SQL,
    SortField.AGENT_ID: "t.agent_id",
    SortField.CUSTOMER_RATING: "t.customer_rating",
    SortField.ISSUE_SUMMARY: "t.issue_summary",
    SortField.UNRESOLVED_AGE_HRS: _UNRESOLVED_AGE_SQL,
    SortField.RESOLUTION_ELAPSED_HRS: _RESOLUTION_ELAPSED_SQL,
}

_AGGREGATION_SQL = {
    Aggregation.AVERAGE: "AVG",
    Aggregation.MINIMUM: "MIN",
    Aggregation.MAXIMUM: "MAX",
    Aggregation.SUM: "SUM",
}


def execute_analytics(
    database_path: str | Path,
    request: AnalyticsRequest,
    reference_clock: ReferenceClock,
) -> AnalyticsExecutionResult:
    """Execute one validated request against SQLite opened read-only."""

    params: dict[str, object] = {
        "reference_time": _sqlite_datetime(reference_clock.timestamp)
    }
    where_sql, applied_range = _build_where(request, reference_clock, params)

    with database_connection(database_path, read_only=True) as connection:
        if request.operation is AnalyticsOperation.LIST:
            return _execute_list(
                connection,
                request,
                reference_clock,
                where_sql,
                params,
                applied_range,
            )
        if request.operation is AnalyticsOperation.COUNT:
            return _execute_count(
                connection,
                reference_clock,
                where_sql,
                params,
                applied_range,
            )
        if request.operation is AnalyticsOperation.AGGREGATE:
            return _execute_aggregate(
                connection,
                request,
                reference_clock,
                where_sql,
                params,
                applied_range,
            )
        return _execute_grouped(
            connection,
            request,
            reference_clock,
            where_sql,
            params,
            applied_range,
        )


def _build_where(
    request: AnalyticsRequest,
    reference_clock: ReferenceClock,
    params: dict[str, object],
) -> tuple[str, DateRange | None]:
    conditions: list[str] = []

    for index, filter_item in enumerate(request.filters):
        expression = _FILTER_SQL[FilterField(filter_item.field)]
        if isinstance(filter_item, EqualityFilter):
            name = f"filter_{index}"
            params[name] = filter_item.value
            operator = "=" if filter_item.operator == "eq" else "!="
            conditions.append(f"{expression} {operator} :{name}")
        elif isinstance(filter_item, MembershipFilter):
            names = []
            for value_index, value in enumerate(filter_item.values):
                name = f"filter_{index}_{value_index}"
                params[name] = value
                names.append(f":{name}")
            conditions.append(f"{expression} IN ({', '.join(names)})")
        elif isinstance(filter_item, NumericComparisonFilter):
            name = f"filter_{index}"
            params[name] = filter_item.value
            operator = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[
                filter_item.operator
            ]
            conditions.append(f"{expression} {operator} :{name}")
        elif isinstance(filter_item, NullFilter):
            operator = "IS NULL" if filter_item.operator == "is_null" else "IS NOT NULL"
            conditions.append(f"{expression} {operator}")
        elif isinstance(filter_item, SummaryContainsFilter):
            name = f"filter_{index}"
            params[name] = filter_item.value
            conditions.append(f"instr(lower({expression}), lower(:{name})) > 0")

    applied_range: DateRange | None = None
    if request.time_filter is not None:
        if request.time_filter.relative_period is not None:
            applied_range = relative_period_range(
                request.time_filter.relative_period,
                reference_clock.timestamp,
            )
        else:
            applied_range = explicit_date_range(
                request.time_filter.start_date,  # type: ignore[arg-type]
                request.time_filter.end_date,  # type: ignore[arg-type]
            )
        params["date_start"] = _sqlite_datetime(applied_range.start)
        params["date_end"] = _sqlite_datetime(applied_range.end)
        time_expression = (
            "datetime(t.created_at)"
            if request.time_filter.field is TicketTimeField.CREATED_AT
            else _RESOLVED_AT_SQL
        )
        conditions.append(
            f"{time_expression} >= datetime(:date_start) "
            f"AND {time_expression} < datetime(:date_end)"
        )

    return (" AND ".join(conditions) if conditions else "1 = 1"), applied_range


def _execute_list(
    connection: sqlite3.Connection,
    request: AnalyticsRequest,
    reference_clock: ReferenceClock,
    where_sql: str,
    params: dict[str, object],
    applied_range: DateRange | None,
) -> ListAnalyticsResult:
    matching_count = int(
        connection.execute(
            f"SELECT COUNT(*) FROM tickets AS t WHERE {where_sql}",
            params,
        ).fetchone()[0]
    )
    selected_sql = ", ".join(
        f"{_OUTPUT_SQL[field]} AS {field.value}" for field in request.selected_fields
    )
    order_sql = _list_order_sql(request)
    semantic_count = min(
        matching_count,
        request.result_limit if request.result_limit is not None else matching_count,
    )
    page_size = min(request.limit, max(0, semantic_count - request.offset))
    query_params = {
        **params,
        "result_limit": page_size,
        "result_offset": request.offset,
    }
    rows = connection.execute(
        f"""
        SELECT {selected_sql}
        FROM tickets AS t
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT :result_limit OFFSET :result_offset
        """,
        query_params,
    ).fetchall()
    result_rows = tuple(
        TicketResultRow(values=_normalize_ticket_row(row, request.selected_fields))
        for row in rows
    )
    return ListAnalyticsResult(
        rows=result_rows,
        selected_fields=request.selected_fields,
        matching_count=matching_count,
        returned_count=len(result_rows),
        offset=request.offset,
        limit=request.limit,
        result_limit=request.result_limit,
        truncated=request.offset + len(result_rows) < matching_count,
        reference_clock=reference_clock,
        applied_date_range=applied_range,
    )


def _execute_count(
    connection: sqlite3.Connection,
    reference_clock: ReferenceClock,
    where_sql: str,
    params: dict[str, object],
    applied_range: DateRange | None,
) -> CountAnalyticsResult:
    value = int(
        connection.execute(
            f"SELECT COUNT(*) FROM tickets AS t WHERE {where_sql}",
            params,
        ).fetchone()[0]
    )
    return CountAnalyticsResult(
        value=value,
        reference_clock=reference_clock,
        applied_date_range=applied_range,
    )


def _execute_aggregate(
    connection: sqlite3.Connection,
    request: AnalyticsRequest,
    reference_clock: ReferenceClock,
    where_sql: str,
    params: dict[str, object],
    applied_range: DateRange | None,
) -> AggregateAnalyticsResult:
    metric = request.metric
    aggregation = request.aggregation
    if metric is None or aggregation is None or aggregation is Aggregation.COUNT:
        raise ValueError(
            "Validated aggregate request is missing metric or aggregation."
        )
    metric_sql = _METRIC_SQL[metric.value]
    function_sql = _AGGREGATION_SQL[aggregation]
    row = connection.execute(
        f"""
        SELECT
            {function_sql}({metric_sql}) AS value,
            COUNT(*) AS matched_row_count,
            COUNT({metric_sql}) AS contributing_count
        FROM tickets AS t
        WHERE {where_sql}
        """,
        params,
    ).fetchone()
    return AggregateAnalyticsResult(
        aggregation=aggregation,
        metric=metric,
        value=float(row["value"]) if row["value"] is not None else None,
        matched_row_count=int(row["matched_row_count"]),
        contributing_count=int(row["contributing_count"]),
        reference_clock=reference_clock,
        applied_date_range=applied_range,
    )


def _execute_grouped(
    connection: sqlite3.Connection,
    request: AnalyticsRequest,
    reference_clock: ReferenceClock,
    where_sql: str,
    params: dict[str, object],
    applied_range: DateRange | None,
) -> GroupedAnalyticsResult:
    group_by = request.group_by
    aggregation = request.aggregation
    if group_by is None or aggregation is None:
        raise ValueError(
            "Validated grouped request is missing grouping or aggregation."
        )
    group_sql = _GROUP_SQL[group_by]
    if aggregation is Aggregation.COUNT:
        value_sql = "COUNT(*)"
        contribution_sql = "COUNT(*)"
    else:
        if request.metric is None:
            raise ValueError("Validated grouped aggregation is missing its metric.")
        metric_sql = _METRIC_SQL[request.metric.value]
        value_sql = f"{_AGGREGATION_SQL[aggregation]}({metric_sql})"
        contribution_sql = f"COUNT({metric_sql})"

    order_sql = _grouped_order_sql(request)
    rows = connection.execute(
        f"""
        SELECT
            {group_sql} AS group_value,
            {value_sql} AS result,
            {contribution_sql} AS contributing_count
        FROM tickets AS t
        WHERE {where_sql}
        GROUP BY {group_sql}
        ORDER BY {order_sql}
        """,
        params,
    ).fetchall()
    all_rows = [
        GroupedResultRow(
            group_value=str(row["group_value"]),
            value=row["result"],
            contributing_count=int(row["contributing_count"]),
        )
        for row in rows
    ]
    semantic_rows, semantic_ties_extended = _apply_grouped_result_limit(
        all_rows, request
    )
    page, page_ties_extended = _slice_grouped_rows(semantic_rows, request)
    return GroupedAnalyticsResult(
        aggregation=aggregation,
        metric=request.metric,
        group_by=group_by,
        rows=tuple(page),
        matching_group_count=len(all_rows),
        returned_count=len(page),
        offset=request.offset,
        limit=request.limit,
        result_limit=request.result_limit,
        ties_extended=semantic_ties_extended or page_ties_extended,
        truncated=request.offset + len(page) < len(all_rows),
        reference_clock=reference_clock,
        applied_date_range=applied_range,
    )


def _list_order_sql(request: AnalyticsRequest) -> str:
    clauses = [
        f"{_SORT_SQL[item.field]} {'ASC' if item.direction is SortDirection.ASCENDING else 'DESC'}"
        for item in request.sort
    ]
    if SortField.TICKET_ID not in {item.field for item in request.sort}:
        clauses.append("t.ticket_id ASC")
    return ", ".join(clauses)


def _grouped_order_sql(request: AnalyticsRequest) -> str:
    clauses = []
    for item in request.sort:
        expression = "result" if item.field is SortField.RESULT else "group_value"
        direction = "ASC" if item.direction is SortDirection.ASCENDING else "DESC"
        clauses.append(f"{expression} {direction}")
    if not clauses or not any(
        item.field.value == request.group_by.value for item in request.sort
    ):
        clauses.append("group_value ASC")
    return ", ".join(clauses)


def _slice_grouped_rows(
    rows: list[GroupedResultRow],
    request: AnalyticsRequest,
) -> tuple[list[GroupedResultRow], bool]:
    page = rows[request.offset : request.offset + request.limit]
    result_ranked = bool(request.sort) and request.sort[0].field is SortField.RESULT
    if not result_ranked or not page:
        return page, False

    boundary = page[-1].value
    next_index = request.offset + len(page)
    while next_index < len(rows) and rows[next_index].value == boundary:
        page.append(rows[next_index])
        next_index += 1
    return page, len(page) > request.limit


def _apply_grouped_result_limit(
    rows: list[GroupedResultRow],
    request: AnalyticsRequest,
) -> tuple[list[GroupedResultRow], bool]:
    """Apply the question's semantic top-N limit before transport pagination."""

    if request.result_limit is None or request.result_limit >= len(rows):
        return rows, False

    limited = rows[: request.result_limit]
    result_ranked = bool(request.sort) and request.sort[0].field is SortField.RESULT
    if not result_ranked or not limited:
        return limited, False

    boundary = limited[-1].value
    next_index = len(limited)
    while next_index < len(rows) and rows[next_index].value == boundary:
        limited.append(rows[next_index])
        next_index += 1
    return limited, len(limited) > request.result_limit


def _normalize_output(value: object, field: OutputField) -> object:
    if value is not None and field in {OutputField.CREATED_AT, OutputField.RESOLVED_AT}:
        return datetime.fromisoformat(str(value))
    return value


def _normalize_ticket_row(
    row: sqlite3.Row,
    selected_fields: tuple[OutputField, ...],
) -> dict[OutputField, object]:
    return {
        field: _normalize_output(row[field.value], field) for field in selected_fields
    }


def _sqlite_datetime(value: datetime) -> str:
    return value.isoformat(sep=" ", timespec="seconds")
