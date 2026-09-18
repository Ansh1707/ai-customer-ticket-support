"""Literal cue extraction for the bounded ticket query language."""

from __future__ import annotations

import calendar
import re
from datetime import date

from ticket_support_ai.llm_plans import NumericConditionPlan
from ticket_support_ai.schemas import FilterField, TicketTimeField


def _extract_explicit_date_range(text: str) -> tuple[date, date] | None:
    """Parse a same-month English inclusive date range stated by the user."""

    month_names = "|".join(calendar.month_name[1:])
    match = re.search(
        rf"\b(?:from|between)\s+({month_names})\s+(\d{{1,2}})\s+"
        rf"(?:through|to|and)\s+(?:(?:{month_names})\s+)?(\d{{1,2}}),?\s+(\d{{4}})\b",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    month = list(calendar.month_name).index(match.group(1).title())
    try:
        start = date(int(match.group(4)), month, int(match.group(2)))
        end = date(int(match.group(4)), month, int(match.group(3)))
    except ValueError:
        return None
    return (start, end) if start <= end else None


def _contains_word(text: str, value: str) -> bool:
    return re.search(rf"\b{re.escape(value)}\b", text) is not None


def _is_negated_value(text: str, value: str) -> bool:
    return (
        re.search(
            rf"\b(?:not|except|excluding|exclude)\s+(?:a\s+)?{re.escape(value)}\b",
            text,
        )
        is not None
    )


_QUOTED_LITERAL_PATTERN = re.compile(
    r'"(?P<double>[^"\n]+)"|“(?P<smart_double>[^”\n]+)”|'
    r"'(?P<single>[^'\n]+)'|‘(?P<smart_single>[^’\n]+)’"
)


def _quoted_literals(text: str) -> tuple[str, ...]:
    """Return user-delimited literals without treating their contents as commands."""

    return tuple(
        next(value for value in match.groupdict().values() if value is not None).strip()
        for match in _QUOTED_LITERAL_PATTERN.finditer(text)
    )


def _mask_quoted_literals(text: str) -> str:
    """Hide quoted literals from categorical, date, and numeric cue extraction."""

    return _QUOTED_LITERAL_PATTERN.sub(
        lambda match: " " * len(match.group(0)),
        text,
    )


def _extract_summary_literal(text: str) -> str | None:
    """Extract a literal issue-summary search term from quoted or simple wording."""

    instruction_text = _mask_quoted_literals(text)
    if not re.search(r"\b(?:issue\s+)?summar(?:y|ies)\b", instruction_text):
        return None
    if not re.search(
        r"\b(?:contain|contains|containing|mention|mentions|search)\b", instruction_text
    ):
        return None

    quoted = _quoted_literals(text)
    if quoted:
        return quoted[0] or None

    match = re.search(
        r"\b(?:contain|contains|containing|mention|mentions|search(?:es|ed)?(?:\s+for)?)\s+"
        r"(?:the\s+)?(?:literal\s+)?(?:text\s+)?(?P<value>.+?)(?:[?.!]|$)",
        text,
    )
    if match is None:
        return None
    value = re.split(
        r"\s+(?:and|with)\s+(?=(?:status|priority|category|created|resolved|"
        r"response|resolution|customer)\b)",
        match.group("value"),
        maxsplit=1,
    )[0].strip()
    return value or None


def _explicit_time_field(
    text: str,
    *,
    default: TicketTimeField = TicketTimeField.CREATED_AT,
) -> TicketTimeField:
    """Choose the event explicitly named by the user, independent of status words."""

    if re.search(r"\b(created|opened|submitted|received)\b", text):
        return TicketTimeField.CREATED_AT
    if re.search(r"\b(resolved|resolution|completed|closed)\b", text):
        return TicketTimeField.RESOLVED_AT
    return default


def _extract_numeric_conditions(text: str) -> tuple[NumericConditionPlan, ...]:
    """Extract every explicit numeric comparison stated in common ticket language."""

    labels = {
        "response time": FilterField.RESPONSE_TIME_HRS,
        "resolution time": FilterField.RESOLUTION_TIME_HRS,
        "customer rating": FilterField.CUSTOMER_RATING,
        "satisfaction score": FilterField.CUSTOMER_RATING,
        "rating": FilterField.CUSTOMER_RATING,
    }
    operators = {
        "greater than": "gt",
        "more than": "gt",
        "above": "gt",
        "over": "gt",
        "at least": "gte",
        "less than": "lt",
        "below": "lt",
        "under": "lt",
        "at most": "lte",
        "equal to": "eq",
        "equals": "eq",
        "of": "eq",
    }
    label_pattern = "|".join(
        re.escape(label) for label in sorted(labels, key=len, reverse=True)
    )
    operator_pattern = "|".join(
        re.escape(operator) for operator in sorted(operators, key=len, reverse=True)
    )
    pattern = re.compile(
        rf"\b(?P<label>{label_pattern})\b\s*(?:is\s+)?"
        rf"(?P<operator>{operator_pattern})\s*"
        rf"(?P<value>\d+(?:\.\d+)?)\b"
    )
    conditions: list[NumericConditionPlan] = []
    seen: set[tuple[FilterField, str, float]] = set()
    unresolved_match = re.search(
        r"not resolved within\s+(\d+(?:\.\d+)?)\s*hours?",
        text,
    )
    if unresolved_match is not None:
        value = float(unresolved_match.group(1))
        key = (FilterField.RESOLUTION_ELAPSED_HRS, "gt", value)
        seen.add(key)
        conditions.append(
            NumericConditionPlan(
                field=FilterField.RESOLUTION_ELAPSED_HRS,
                operator="gt",
                value=value,
            )
        )
    for match in pattern.finditer(text):
        field = labels[match.group("label")]
        operator = operators[match.group("operator")]
        value = float(match.group("value"))
        key = (field, operator, value)
        if key in seen:
            continue
        seen.add(key)
        conditions.append(
            NumericConditionPlan(field=field, operator=operator, value=value)
        )
    return tuple(conditions)
