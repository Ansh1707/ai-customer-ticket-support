"""Explicit bounded language capabilities checked independently of model output.

This gate recognizes documented unsupported families; it is not a proof of
arbitrary natural-language equivalence. Quoted search values are excluded.
"""

from __future__ import annotations

import re

from ticket_support_ai.schemas import ClarificationRequest, NullFilter

UNSUPPORTED_CAPABILITIES = {
    "statistics": "Median, percentile, percentage, and ratio calculations are not supported. Ask for a count or an average instead.",
    "boolean": "OR is supported only between values of the same categorical field. Split cross-field or nested Boolean questions into separate queries.",
    "dates": "Only one event date range is supported per question. Ask separately about creation and resolution dates.",
    "limit": "Request between 1 and 100 results using a numeric result count.",
}


def instruction_text(question: str) -> str:
    return re.sub(r'"[^"\n]*"|“[^”\n]*”|\'[^\'\n]*\'', " ", question.casefold())


def extract_result_limit(text: str) -> int | None:
    match = re.search(
        r"\b(?:top|bottom|first|last|show|list|which|give|return)\s+"
        r"(?:me\s+)?(?:the\s+)?(\d+)\s*\b",
        text,
    )
    return int(match.group(1)) if match else None


def extract_null_conditions(text: str) -> tuple[NullFilter, ...]:
    conditions = []
    for label, field in (
        (r"(?:customer\s+)?rating", "customer_rating"),
        (r"resolution\s+time", "resolution_time_hrs"),
    ):
        missing = re.search(
            rf"\b(?:no|missing|without|unknown|null)\s+(?:a\s+)?{label}\b|"
            rf"\b{label}\s+(?:is\s+)?(?:missing|null|unknown|absent)\b",
            text,
        )
        present = re.search(
            rf"\b{label}\s+(?:is\s+)?(?:not\s+null|present|available)\b|"
            rf"\b(?:with|has|have)\s+(?:a\s+)?(?:recorded|non-null)\s+{label}\b",
            text,
        )
        if missing or present:
            conditions.append(
                NullFilter(
                    field=field, operator="is_null" if missing else "is_not_null"
                )
            )
    return tuple(conditions)


def capability_limitation(question: str) -> ClarificationRequest | None:
    text = instruction_text(question)
    reason = None
    if re.search(
        r"\b(?:median|percentile|percentage|percent|proportion|fraction|ratio)\b|%",
        text,
    ):
        reason = UNSUPPORTED_CAPABILITIES["statistics"]
    elif re.search(r"\bor\b", text):
        # Admit only homogeneous categorical alternatives; never silently turn
        # a disjunction of different fields/numeric expressions into conjunction.
        safe = text
        for values in (
            "low|medium|high|critical",
            "open|resolved|escalated",
            "billing|technical|general",
        ):
            safe = re.sub(
                rf"\b(?:{values})(?:\s+or\s+(?:{values}))+\b",
                " categorical_alternatives ",
                safe,
            )
        if re.search(r"\bor\b", safe):
            reason = UNSUPPORTED_CAPABILITIES["boolean"]
    if (
        reason is None
        and re.search(
            r"\b(?:created|opened|submitted|received)\s+(?:in|during|from|between|since|before|after)\b",
            text,
        )
        and re.search(
            r"\b(?:resolved|completed|closed)\s+(?:in|during|from|between|since|before|after)\b",
            text,
        )
    ):
        reason = UNSUPPORTED_CAPABILITIES["dates"]
    count = extract_result_limit(text)
    if reason is None and count is not None and not 1 <= count <= 100:
        reason = UNSUPPORTED_CAPABILITIES["limit"]
    if reason is None:
        return None
    return ClarificationRequest(
        question=reason,
        reason="The requested capability cannot be represented safely; no data query was executed.",
    )
