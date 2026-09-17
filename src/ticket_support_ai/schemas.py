"""Pydantic models shared by the application layers."""

import math
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)


class TicketCategory(StrEnum):
    """Supported ticket categories from the assessment schema."""

    BILLING = "Billing"
    TECHNICAL = "Technical"
    GENERAL = "General"


class TicketPriority(StrEnum):
    """Supported ticket priority levels from the assessment schema."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class TicketStatus(StrEnum):
    """Supported ticket states from the assessment schema."""

    OPEN = "Open"
    RESOLVED = "Resolved"
    ESCALATED = "Escalated"


class ReferenceMode(StrEnum):
    """Available sources for the application's reference clock."""

    DATASET = "dataset"
    CURRENT = "current"
    CUSTOM = "custom"


class RelativePeriod(StrEnum):
    """Supported calendar periods relative to a reference timestamp."""

    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"


class TicketTimeField(StrEnum):
    """Ticket timestamp used when applying a date range."""

    CREATED_AT = "created_at"
    RESOLVED_AT = "resolved_at"


class QueryIntent(StrEnum):
    """Top-level interpretation selected for a natural-language request."""

    ANALYTICS = "analytics"
    ANOMALIES = "anomalies"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"


class AnalyticsOperation(StrEnum):
    """Supported deterministic analytics result shapes."""

    LIST = "list"
    COUNT = "count"
    AGGREGATE = "aggregate"
    GROUPED_AGGREGATE = "grouped_aggregate"


class Aggregation(StrEnum):
    """Supported aggregate calculations."""

    COUNT = "count"
    AVERAGE = "average"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    SUM = "sum"


class FilterField(StrEnum):
    """Fields that may participate in validated row filters."""

    TICKET_ID = "ticket_id"
    CATEGORY = "category"
    PRIORITY = "priority"
    STATUS = "status"
    RESPONSE_TIME_HRS = "response_time_hrs"
    RESOLUTION_TIME_HRS = "resolution_time_hrs"
    AGENT_ID = "agent_id"
    CUSTOMER_RATING = "customer_rating"
    ISSUE_SUMMARY = "issue_summary"
    RESOLUTION_ELAPSED_HRS = "resolution_elapsed_hrs"


class OutputField(StrEnum):
    """Fields that a list query may return."""

    TICKET_ID = "ticket_id"
    CREATED_AT = "created_at"
    CATEGORY = "category"
    PRIORITY = "priority"
    STATUS = "status"
    RESPONSE_TIME_HRS = "response_time_hrs"
    RESOLUTION_TIME_HRS = "resolution_time_hrs"
    RESOLVED_AT = "resolved_at"
    AGENT_ID = "agent_id"
    CUSTOMER_RATING = "customer_rating"
    ISSUE_SUMMARY = "issue_summary"
    UNRESOLVED_AGE_HRS = "unresolved_age_hrs"
    RESOLUTION_ELAPSED_HRS = "resolution_elapsed_hrs"


class MetricField(StrEnum):
    """Numeric fields allowed in aggregate operations."""

    RESPONSE_TIME_HRS = "response_time_hrs"
    RESOLUTION_TIME_HRS = "resolution_time_hrs"
    CUSTOMER_RATING = "customer_rating"


class GroupField(StrEnum):
    """Categorical dimensions allowed for grouped aggregation."""

    AGENT_ID = "agent_id"
    CATEGORY = "category"
    PRIORITY = "priority"
    STATUS = "status"


class SortField(StrEnum):
    """Allowlisted sort targets; result is the calculated aggregate value."""

    RESULT = "result"
    TICKET_ID = "ticket_id"
    CREATED_AT = "created_at"
    CATEGORY = "category"
    PRIORITY = "priority"
    STATUS = "status"
    RESPONSE_TIME_HRS = "response_time_hrs"
    RESOLUTION_TIME_HRS = "resolution_time_hrs"
    RESOLVED_AT = "resolved_at"
    AGENT_ID = "agent_id"
    CUSTOMER_RATING = "customer_rating"
    ISSUE_SUMMARY = "issue_summary"
    UNRESOLVED_AGE_HRS = "unresolved_age_hrs"
    RESOLUTION_ELAPSED_HRS = "resolution_elapsed_hrs"


class SortDirection(StrEnum):
    """Supported deterministic sort directions."""

    ASCENDING = "asc"
    DESCENDING = "desc"


class AnomalyRule(StrEnum):
    """Anomaly rule selection understood by the interpreter contract."""

    ALL = "all"
    LONG_RESOLUTION = "long_resolution"
    OVERDUE_HIGH_PRIORITY = "overdue_high_priority"
    RESOLUTION_BEFORE_RESPONSE = "resolution_before_response"


class TicketRecord(BaseModel):
    """One validated and typed support-ticket record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticket_id: str
    created_at: datetime
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    response_time_hrs: float
    resolution_time_hrs: float | None
    agent_id: str
    customer_rating: int | None
    issue_summary: str


class ValidationLevel(StrEnum):
    """Severity attached to a CSV validation issue."""

    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(BaseModel):
    """Actionable location and explanation for one validation finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: ValidationLevel
    code: str
    message: str
    row_number: int | None = None
    field: str | None = None
    ticket_id: str | None = None


class ValidatedCSV(BaseModel):
    """Validated source metadata, typed rows, and non-blocking warnings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_path: Path
    source_sha256: str
    row_count: int
    tickets: tuple[TicketRecord, ...]
    warnings: tuple[ValidationIssue, ...] = ()


class IngestionResult(BaseModel):
    """Outcome and persisted metadata for one SQLite snapshot ingestion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    database_path: Path
    source_path: Path
    source_sha256: str
    row_count: int
    warning_count: int
    ingested_at: datetime
    reused_existing: bool


class DateWarning(BaseModel):
    """Non-blocking warning produced while resolving date semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str


class ReferenceClock(BaseModel):
    """Resolved reference timestamp and its visible provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ReferenceMode
    timestamp: datetime
    dataset_default: datetime | None
    warnings: tuple[DateWarning, ...] = ()

    @model_validator(mode="after")
    def timestamps_are_dataset_local(self) -> "ReferenceClock":
        if self.timestamp.tzinfo is not None:
            raise ValueError("Reference timestamp must not include a timezone.")
        if self.dataset_default is not None and self.dataset_default.tzinfo is not None:
            raise ValueError("Dataset default timestamp must not include a timezone.")
        return self


class DateRange(BaseModel):
    """Half-open dataset-local range: start is included and end is excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime
    end: datetime
    label: str

    @model_validator(mode="after")
    def valid_half_open_range(self) -> "DateRange":
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("Date-range timestamps must not include a timezone.")
        if self.end < self.start:
            raise ValueError("Date-range end cannot be earlier than its start.")
        return self

    def contains(self, value: datetime) -> bool:
        """Return whether a timestamp falls inside the half-open range."""

        if value.tzinfo is not None:
            raise ValueError("Compared timestamp must not include a timezone.")
        return self.start <= value < self.end


ScalarFilterValue: TypeAlias = str | float | int


class EqualityFilter(BaseModel):
    """Exact or negated match against one allowlisted field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: FilterField
    operator: Literal["eq", "ne"]
    value: ScalarFilterValue

    @model_validator(mode="after")
    def valid_field_value(self) -> "EqualityFilter":
        _validate_scalar_filter_value(self.field, self.value)
        return self


class MembershipFilter(BaseModel):
    """Match any value from a nonempty allowlisted set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: FilterField
    operator: Literal["in"]
    values: tuple[ScalarFilterValue, ...]

    @model_validator(mode="after")
    def valid_membership(self) -> "MembershipFilter":
        allowed_fields = {
            FilterField.TICKET_ID,
            FilterField.CATEGORY,
            FilterField.PRIORITY,
            FilterField.STATUS,
            FilterField.AGENT_ID,
            FilterField.CUSTOMER_RATING,
        }
        if self.field not in allowed_fields:
            raise ValueError(f"Membership filtering is not supported for {self.field}.")
        if not self.values:
            raise ValueError("Membership filter requires at least one value.")
        for value in self.values:
            _validate_scalar_filter_value(self.field, value)
        normalized = tuple((type(value).__name__, value) for value in self.values)
        if len(set(normalized)) != len(normalized):
            raise ValueError("Membership filter values must be unique.")
        return self


class NumericComparisonFilter(BaseModel):
    """Compare one numeric field against a finite nonnegative value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: FilterField
    operator: Literal["gt", "gte", "lt", "lte"]
    value: float

    @model_validator(mode="after")
    def numeric_field_and_value(self) -> "NumericComparisonFilter":
        if self.field not in _NUMERIC_FILTER_FIELDS:
            raise ValueError(f"Numeric comparison is not supported for {self.field}.")
        if not math.isfinite(self.value) or self.value < 0:
            raise ValueError("Numeric comparison value must be finite and nonnegative.")
        return self


class NullFilter(BaseModel):
    """Test whether one nullable field is null or non-null."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: FilterField
    operator: Literal["is_null", "is_not_null"]

    @model_validator(mode="after")
    def nullable_field(self) -> "NullFilter":
        if self.field not in _NULLABLE_FILTER_FIELDS:
            raise ValueError(f"Null filtering is not supported for {self.field}.")
        return self


class SummaryContainsFilter(BaseModel):
    """Case-insensitive literal substring search over issue summaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: Literal["issue_summary"] = "issue_summary"
    operator: Literal["contains"] = "contains"
    value: str
    case_sensitive: Literal[False] = False

    @field_validator("value")
    @classmethod
    def nonblank_literal(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Issue-summary search value must not be blank.")
        return value


AnalyticsFilter: TypeAlias = Annotated[
    EqualityFilter
    | MembershipFilter
    | NumericComparisonFilter
    | NullFilter
    | SummaryContainsFilter,
    Field(discriminator="operator"),
]


class TimeFilter(BaseModel):
    """Relative calendar period or explicit inclusive date range."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: TicketTimeField
    relative_period: RelativePeriod | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def exactly_one_period_form(self) -> "TimeFilter":
        has_relative = self.relative_period is not None
        has_start = self.start_date is not None
        has_end = self.end_date is not None
        if has_relative and (has_start or has_end):
            raise ValueError(
                "Time filter cannot combine a relative period with explicit dates."
            )
        if not has_relative and not (has_start and has_end):
            raise ValueError(
                "Time filter requires a relative period or both explicit dates."
            )
        if has_start != has_end:
            raise ValueError("Explicit time filter requires both start and end dates.")
        if has_start and self.end_date < self.start_date:  # type: ignore[operator]
            raise ValueError("Explicit time-filter end date cannot precede its start.")
        return self


class SortSpec(BaseModel):
    """One deterministic allowlisted sort instruction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: SortField
    direction: SortDirection = SortDirection.ASCENDING


class AnalyticsRequest(BaseModel):
    """Validated analytics plan that can be translated to deterministic SQL."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: Literal[QueryIntent.ANALYTICS] = QueryIntent.ANALYTICS
    operation: AnalyticsOperation
    filters: tuple[AnalyticsFilter, ...] = ()
    selected_fields: tuple[OutputField, ...] = ()
    metric: MetricField | None = None
    aggregation: Aggregation | None = None
    group_by: GroupField | None = None
    sort: tuple[SortSpec, ...] = ()
    time_filter: TimeFilter | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def operation_contract(self) -> "AnalyticsRequest":
        if len(set(self.selected_fields)) != len(self.selected_fields):
            raise ValueError("Selected output fields must be unique.")
        sort_fields = tuple(item.field for item in self.sort)
        if len(set(sort_fields)) != len(sort_fields):
            raise ValueError("Sort fields must be unique.")

        if self.operation is AnalyticsOperation.LIST:
            if not self.selected_fields:
                raise ValueError("List operation requires selected output fields.")
            if any(
                value is not None
                for value in (self.metric, self.aggregation, self.group_by)
            ):
                raise ValueError(
                    "List operation cannot define metric, aggregation, or grouping."
                )
            if SortField.RESULT in sort_fields:
                raise ValueError("List operation cannot sort by aggregate result.")

        elif self.operation is AnalyticsOperation.COUNT:
            if (
                self.selected_fields
                or self.sort
                or self.limit != 50
                or self.offset != 0
                or any(
                value is not None
                for value in (self.metric, self.aggregation, self.group_by)
                )
            ):
                raise ValueError(
                    "Count operation accepts filters, time filter, and default paging only."
                )

        elif self.operation is AnalyticsOperation.AGGREGATE:
            if (
                self.selected_fields
                or self.group_by is not None
                or self.sort
                or self.limit != 50
                or self.offset != 0
            ):
                raise ValueError(
                    "Aggregate operation cannot select fields, group, or sort."
                )
            if self.metric is None or self.aggregation is None:
                raise ValueError("Aggregate operation requires metric and aggregation.")
            if self.aggregation is Aggregation.COUNT:
                raise ValueError("Use count operation for an ungrouped count.")

        else:
            if self.selected_fields:
                raise ValueError(
                    "Grouped aggregate operation cannot select ticket output fields."
                )
            if self.group_by is None or self.aggregation is None:
                raise ValueError(
                    "Grouped aggregate operation requires group_by and aggregation."
                )
            if self.aggregation is Aggregation.COUNT:
                if self.metric is not None:
                    raise ValueError("Grouped count must not define a metric.")
            elif self.metric is None:
                raise ValueError(
                    "Grouped non-count aggregation requires a numeric metric."
                )
            allowed_sorts = {
                SortField.RESULT,
                SortField(self.group_by.value),
            }
            if any(field not in allowed_sorts for field in sort_fields):
                raise ValueError(
                    "Grouped aggregate may sort only by its group or result."
                )
        return self


class AnomalyQueryRequest(BaseModel):
    """Validated request to route a question to deterministic anomaly rules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: Literal[QueryIntent.ANOMALIES] = QueryIntent.ANOMALIES
    rule: AnomalyRule = AnomalyRule.ALL
    time_filter: TimeFilter | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1_000_000)


class ClarificationRequest(BaseModel):
    """Interpreter result when a material user choice is missing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: Literal[QueryIntent.CLARIFICATION] = QueryIntent.CLARIFICATION
    question: str
    reason: str

    @field_validator("question", "reason")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Clarification text must not be blank.")
        return value


class UnsupportedRequest(BaseModel):
    """Interpreter result for a request outside the supported analytics scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: Literal[QueryIntent.UNSUPPORTED] = QueryIntent.UNSUPPORTED
    reason: str

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Unsupported-request reason must not be blank.")
        return value


QueryRequest: TypeAlias = Annotated[
    AnalyticsRequest
    | AnomalyQueryRequest
    | ClarificationRequest
    | UnsupportedRequest,
    Field(discriminator="intent"),
]

QUERY_REQUEST_ADAPTER = TypeAdapter(QueryRequest)


def parse_query_request(payload: object) -> QueryRequest:
    """Validate untrusted structured output against the complete request contract."""

    return QUERY_REQUEST_ADAPTER.validate_python(payload)


ResultValue: TypeAlias = str | int | float | datetime | None


class TicketResultRow(BaseModel):
    """One selected ticket row keyed by allowlisted output fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    values: dict[OutputField, ResultValue]


class ListAnalyticsResult(BaseModel):
    """Paginated result for a ticket-list request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal[AnalyticsOperation.LIST] = AnalyticsOperation.LIST
    rows: tuple[TicketResultRow, ...]
    selected_fields: tuple[OutputField, ...]
    matching_count: int
    returned_count: int
    offset: int
    limit: int
    truncated: bool
    reference_clock: ReferenceClock
    applied_date_range: DateRange | None = None


class CountAnalyticsResult(BaseModel):
    """Scalar count result, including zero for no matches."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal[AnalyticsOperation.COUNT] = AnalyticsOperation.COUNT
    value: int
    reference_clock: ReferenceClock
    applied_date_range: DateRange | None = None


class AggregateAnalyticsResult(BaseModel):
    """Scalar aggregate and the number of non-null contributing values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal[AnalyticsOperation.AGGREGATE] = AnalyticsOperation.AGGREGATE
    aggregation: Aggregation
    metric: MetricField
    value: float | None
    matched_row_count: int
    contributing_count: int
    reference_clock: ReferenceClock
    applied_date_range: DateRange | None = None


class GroupedResultRow(BaseModel):
    """One grouped aggregate result and its non-null contribution count."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_value: str
    value: int | float | None
    contributing_count: int


class GroupedAnalyticsResult(BaseModel):
    """Paginated grouped aggregate with tie-preserving result limits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal[AnalyticsOperation.GROUPED_AGGREGATE] = (
        AnalyticsOperation.GROUPED_AGGREGATE
    )
    aggregation: Aggregation
    metric: MetricField | None
    group_by: GroupField
    rows: tuple[GroupedResultRow, ...]
    matching_group_count: int
    returned_count: int
    offset: int
    limit: int
    ties_extended: bool
    truncated: bool
    reference_clock: ReferenceClock
    applied_date_range: DateRange | None = None


AnalyticsExecutionResult: TypeAlias = (
    ListAnalyticsResult
    | CountAnalyticsResult
    | AggregateAnalyticsResult
    | GroupedAnalyticsResult
)


class LongResolutionBaseline(BaseModel):
    """Auditable IQR statistics for resolved-ticket resolution durations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_size: int = Field(ge=4)
    quartile_method: Literal["linear_type_7"] = "linear_type_7"
    q1_hrs: float = Field(ge=0)
    q3_hrs: float = Field(ge=0)
    iqr_hrs: float = Field(ge=0)
    multiplier: float = Field(default=1.5, ge=0)
    upper_fence_hrs: float = Field(ge=0)


class AnomalyFlag(BaseModel):
    """One deterministic rule violation attached to a ticket."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: AnomalyRule
    observed_value_hrs: float = Field(ge=0)
    threshold_hrs: float = Field(ge=0)
    event_at: datetime
    reason: str

    @model_validator(mode="after")
    def concrete_rule_and_exceeded_threshold(self) -> "AnomalyFlag":
        if self.rule is AnomalyRule.ALL:
            raise ValueError("An anomaly flag must identify one concrete rule.")
        if self.observed_value_hrs <= self.threshold_hrs:
            raise ValueError("An anomaly flag must strictly exceed its threshold.")
        if not self.reason.strip():
            raise ValueError("An anomaly flag requires a nonblank explanation.")
        return self


class AnomalyTicket(BaseModel):
    """One uniquely flagged ticket with all of its triggered rules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticket_id: str
    created_at: datetime
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    agent_id: str
    issue_summary: str
    response_time_hrs: float
    resolution_time_hrs: float | None
    unresolved_age_hrs: float | None
    flags: tuple[AnomalyFlag, ...]

    @model_validator(mode="after")
    def has_unique_flags(self) -> "AnomalyTicket":
        rules = tuple(flag.rule for flag in self.flags)
        if not rules:
            raise ValueError("An anomaly ticket requires at least one flag.")
        if len(set(rules)) != len(rules):
            raise ValueError("An anomaly ticket cannot repeat the same rule.")
        return self


class AnomalyRuleCounts(BaseModel):
    """Unpaginated number of flagged tickets for each concrete rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    long_resolution: int = Field(ge=0)
    overdue_high_priority: int = Field(ge=0)
    resolution_before_response: int = Field(ge=0)


class AnomalyDetectionResult(BaseModel):
    """Paginated, explainable and auditable anomaly-detection result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_rule: AnomalyRule
    tickets: tuple[AnomalyTicket, ...]
    matching_ticket_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    rule_counts: AnomalyRuleCounts
    long_resolution_baseline: LongResolutionBaseline | None
    overdue_threshold_hrs: float = Field(default=24.0, ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    truncated: bool
    reference_clock: ReferenceClock
    applied_date_range: DateRange | None = None
    warnings: tuple[str, ...] = ()


QueryExecutionData: TypeAlias = AnalyticsExecutionResult | AnomalyDetectionResult


class QueryOutcome(StrEnum):
    """Successful public outcome of a natural-language query."""

    OK = "ok"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"


class QueryTiming(BaseModel):
    """Measured server-side stages for one successfully handled query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interpretation_ms: float = Field(ge=0)
    execution_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class NaturalLanguageQueryResult(BaseModel):
    """Complete interpreted query response with deterministic supporting evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str
    outcome: QueryOutcome
    answer: str
    interpretation: QueryRequest
    data: QueryExecutionData | None = None
    reference_clock: ReferenceClock
    warnings: tuple[str, ...] = ()
    matching_count: int | None = Field(default=None, ge=0)
    timing: QueryTiming

    @model_validator(mode="after")
    def result_matches_interpretation(self) -> "NaturalLanguageQueryResult":
        needs_data = self.interpretation.intent in {
            QueryIntent.ANALYTICS,
            QueryIntent.ANOMALIES,
        }
        if needs_data != (self.data is not None):
            raise ValueError(
                "Analytics and anomaly interpretations require data; clarification "
                "and unsupported interpretations must not contain data."
            )
        expected_outcome = {
            QueryIntent.ANALYTICS: QueryOutcome.OK,
            QueryIntent.ANOMALIES: QueryOutcome.OK,
            QueryIntent.CLARIFICATION: QueryOutcome.CLARIFICATION,
            QueryIntent.UNSUPPORTED: QueryOutcome.UNSUPPORTED,
        }[self.interpretation.intent]
        if self.outcome is not expected_outcome:
            raise ValueError("Query outcome must match the interpretation intent.")
        if needs_data != (self.matching_count is not None):
            raise ValueError(
                "Executed queries require matching_count; nonexecution outcomes do not."
            )
        if not self.question.strip() or not self.answer.strip():
            raise ValueError("Query result question and answer must not be blank.")
        return self


_NUMERIC_FILTER_FIELDS = {
    FilterField.RESPONSE_TIME_HRS,
    FilterField.RESOLUTION_TIME_HRS,
    FilterField.CUSTOMER_RATING,
    FilterField.RESOLUTION_ELAPSED_HRS,
}
_NULLABLE_FILTER_FIELDS = {
    FilterField.RESOLUTION_TIME_HRS,
    FilterField.CUSTOMER_RATING,
}


def _validate_scalar_filter_value(
    field: FilterField,
    value: ScalarFilterValue,
) -> None:
    if isinstance(value, bool):
        # Pydantic wraps ValueError from validators into a structured ValidationError.
        raise ValueError("Boolean filter values are not supported.")  # noqa: TRY004

    enum_types = {
        FilterField.CATEGORY: TicketCategory,
        FilterField.PRIORITY: TicketPriority,
        FilterField.STATUS: TicketStatus,
    }
    enum_type = enum_types.get(field)
    if enum_type is not None:
        if not isinstance(value, str):
            raise ValueError(f"{field} requires a string value.")
        try:
            enum_type(value)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in enum_type)
            raise ValueError(
                f"Invalid {field} value {value!r}; expected one of [{allowed}]."
            ) from exc
        return

    if field in _NUMERIC_FILTER_FIELDS:
        if not isinstance(value, (int, float)):
            raise ValueError(f"{field} requires a numeric value.")
        numeric_value = float(value)
        if not math.isfinite(numeric_value) or numeric_value < 0:
            raise ValueError(f"{field} value must be finite and nonnegative.")
        if field is FilterField.CUSTOMER_RATING and (
            not numeric_value.is_integer() or not 1 <= numeric_value <= 5
        ):
            raise ValueError("Customer rating filter must be an integer from 1 to 5.")
        return

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} requires a nonblank string value.")
