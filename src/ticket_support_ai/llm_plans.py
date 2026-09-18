"""Compact model-facing contracts; execution contracts live in schemas."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ticket_support_ai.schemas import (
    Aggregation,
    AnalyticsOperation,
    FilterField,
    GroupField,
    MetricField,
    NullFilter,
    QueryIntent,
    RelativePeriod,
    SortDirection,
    SortField,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    TicketTimeField,
)


class OllamaModelStatus(BaseModel):
    """Readiness details suitable for the later health endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = "ollama"
    model: str
    service_available: bool
    model_available: bool
    version: str | None = None
    error: str | None = None


class IntentRoute(BaseModel):
    """Small first-stage schema that avoids union confusion on compact models."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: QueryIntent


class NumericConditionPlan(BaseModel):
    """One model-facing numeric condition preserved before strict compilation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: Literal[
        FilterField.RESPONSE_TIME_HRS,
        FilterField.RESOLUTION_TIME_HRS,
        FilterField.CUSTOMER_RATING,
        FilterField.RESOLUTION_ELAPSED_HRS,
    ]
    operator: Literal["eq", "gt", "gte", "lt", "lte"]
    value: float = Field(ge=0)


class AnalyticsPlan(BaseModel):
    """Compact model-facing representation compiled to the strict request contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: AnalyticsOperation
    categories: tuple[TicketCategory, ...] = ()
    excluded_categories: tuple[TicketCategory, ...] = ()
    priorities: tuple[TicketPriority, ...] = ()
    excluded_priorities: tuple[TicketPriority, ...] = ()
    statuses: tuple[TicketStatus, ...] = ()
    excluded_statuses: tuple[TicketStatus, ...] = ()
    ticket_ids: tuple[str, ...] = ()
    agent_ids: tuple[str, ...] = ()
    summary_contains: str | None = None
    numeric_conditions: tuple[NumericConditionPlan, ...] = ()
    null_conditions: tuple[NullFilter, ...] = ()
    aggregation: Aggregation | None = None
    metric: MetricField | None = None
    group_by: GroupField | None = None
    time_field: TicketTimeField | None = None
    relative_period: RelativePeriod | None = None
    start_date: date | None = None
    end_date: date | None = None
    sort_field: SortField | None = None
    sort_direction: SortDirection | None = None
    result_limit: int | None = Field(default=None, ge=1, le=100)
