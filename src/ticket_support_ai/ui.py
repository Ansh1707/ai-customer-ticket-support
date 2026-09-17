"""Streamlit interface backed exclusively by the FastAPI service."""

from __future__ import annotations

import os
from datetime import date, datetime, time
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
import streamlit as st

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
SAMPLE_QUESTIONS = (
    "How many tickets are currently open?",
    "Which agent resolved the most tickets this month?",
    "Show me all Critical tickets not resolved within 12 hours.",
    "What is the average customer rating for Technical category tickets?",
    "Are there any anomalies in resolution times this week?",
)
REFERENCE_LABELS = {
    "dataset": "Dataset reference (recommended)",
    "current": "Current computer time",
    "custom": "Custom dataset-local time",
}
ANOMALY_RULE_LABELS = {
    "all": "All anomaly rules",
    "long_resolution": "Abnormally long resolution",
    "overdue_high_priority": "High-priority unresolved over 24 hours",
    "resolution_before_response": "Resolution shorter than first response",
}
PERIOD_LABELS = {
    "": "All dates",
    "this_week": "This week",
    "last_week": "Last week",
    "this_month": "This month",
    "last_month": "Last month",
}
TIME_FIELD_LABELS = {
    "": "Automatic for selected rule",
    "created_at": "Ticket creation time",
    "resolved_at": "Inferred resolution time",
}


class TicketAPI(Protocol):
    """Small API boundary used by the UI and its component tests."""

    def health(self) -> dict[str, Any]: ...

    def query(
        self,
        question: str,
        reference_mode: str,
        custom_reference: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]: ...

    def anomalies(self, params: dict[str, Any]) -> dict[str, Any]: ...


class UIAPIError(RuntimeError):
    """Safe API failure suitable for direct display in Streamlit."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "api_error",
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class TicketAPIClient:
    """Synchronous HTTP client for Streamlit's rerun execution model."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        selected_url = (
            base_url or os.getenv("TICKET_API_BASE_URL", DEFAULT_API_BASE_URL)
        ).rstrip("/")
        parsed = urlparse(selected_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("TICKET_API_BASE_URL must be an absolute HTTP(S) URL.")
        self.base_url = selected_url
        self.transport = transport

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", timeout=5.0)

    def query(
        self,
        question: str,
        reference_mode: str = "dataset",
        custom_reference: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "question": question,
            "reference_mode": reference_mode,
            "limit": limit,
            "offset": offset,
        }
        if custom_reference is not None:
            payload["custom_reference"] = custom_reference
        return self._request("POST", "/query", json=payload, timeout=100.0)

    def anomalies(self, params: dict[str, Any]) -> dict[str, Any]:
        cleaned = {key: value for key, value in params.items() if value is not None}
        return self._request("GET", "/anomalies", params=cleaned, timeout=15.0)

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            with httpx.Client(
                base_url=self.base_url,
                transport=self.transport,
                timeout=timeout,
            ) as client:
                response = client.request(method, path, **kwargs)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise UIAPIError(
                "The API did not respond in time. Check the local services and retry.",
                code="api_timeout",
            ) from exc
        except httpx.ConnectError as exc:
            raise UIAPIError(
                f"Cannot connect to the API at {self.base_url}. Start the API and retry.",
                code="api_unavailable",
            ) from exc
        except httpx.HTTPStatusError as exc:
            message, code = _api_error_detail(exc.response)
            raise UIAPIError(
                message,
                code=code,
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise UIAPIError(
                "The API request failed. Check the API terminal for details.",
                code="api_request_failed",
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise UIAPIError(
                "The API returned an invalid JSON response.",
                code="invalid_api_response",
            ) from exc
        if not isinstance(payload, dict):
            raise UIAPIError(
                "The API returned an unexpected response.",
                code="invalid_api_response",
            )
        return payload


def render_app(api_client: TicketAPI | None = None) -> None:
    """Render the complete Streamlit page using only the public REST API."""

    client = api_client or TicketAPIClient()
    st.set_page_config(
        page_title="AI Customer Ticket Support",
        page_icon="🎫",
        layout="wide",
    )
    st.title("AI Customer Ticket Support")
    st.caption(
        "Ask questions with local Qwen and inspect deterministic ticket analytics."
    )

    _render_health(client)
    query_tab, anomaly_tab, guide_tab = st.tabs(
        ["Ask the dataset", "Review anomalies", "Usage guide"]
    )
    with query_tab:
        _render_query_tab(client)
    with anomaly_tab:
        _render_anomaly_tab(client)
    with guide_tab:
        _render_usage_guide()


def _render_health(client: TicketAPI) -> None:
    with st.sidebar:
        st.header("Service status")
        try:
            health = client.health()
        except UIAPIError as exc:
            st.error(str(exc))
            st.caption("The question and anomaly controls remain available for retry.")
            return

        dataset = health["dataset"]
        model = health["model"]
        if health["status"] == "ready":
            st.success("API, dataset, and model are ready")
        else:
            st.warning("One or more local services are unavailable")
        st.metric("Dataset rows", dataset.get("row_count") or 0)
        if health.get("default_reference"):
            st.caption(
                f"Dataset reference: {health['default_reference']} (dataset-local)"
            )
        st.write(f"**Dataset:** {'Ready' if dataset['available'] else 'Unavailable'}")
        st.write(
            f"**Ollama:** {'Ready' if model['service_available'] else 'Unavailable'}"
        )
        st.write(
            f"**Model `{model['model']}`:** "
            f"{'Ready' if model['model_available'] else 'Unavailable'}"
        )
        if dataset.get("warning_count"):
            st.caption(f"{dataset['warning_count']} preserved source-quality warnings.")
        if dataset.get("error"):
            st.error(dataset["error"])
        if model.get("error"):
            st.error(model["error"])


def _render_query_tab(client: TicketAPI) -> None:
    st.subheader("Ask a question")
    st.write(
        "Qwen interprets the wording; validated Python and SQLite calculate the answer."
    )
    selected_sample = st.selectbox(
        "Sample questions",
        SAMPLE_QUESTIONS,
        key="selected_sample",
    )
    if "query_question" not in st.session_state:
        st.session_state.query_question = SAMPLE_QUESTIONS[0]
    if st.button("Use selected sample", key="use_sample"):
        st.session_state.query_question = selected_sample
        st.rerun()

    question = st.text_area(
        "Question",
        key="query_question",
        height=100,
        max_chars=2000,
    )
    reference_mode, custom_reference = _reference_controls("query")
    first, second = st.columns(2)
    limit = first.number_input(
        "Rows per page", min_value=1, max_value=100, value=50, step=1
    )
    offset = second.number_input(
        "Offset", min_value=0, max_value=1_000_000, value=0, step=1
    )
    submitted = st.button("Ask Qwen", type="primary", key="submit_query")

    st.caption(
        "The supplied file is a current-status snapshot and cannot reconstruct "
        "historical status changes."
    )
    if submitted:
        try:
            st.session_state.query_result = client.query(
                question,
                reference_mode,
                custom_reference,
                int(limit),
                int(offset),
            )
            st.session_state.pop("query_error", None)
        except UIAPIError as exc:
            st.session_state.query_error = str(exc)
            st.session_state.pop("query_result", None)

    if error := st.session_state.get("query_error"):
        st.error(error)
    result = st.session_state.get("query_result")
    if result:
        _render_query_result(result)


def _render_query_result(result: dict[str, Any]) -> None:
    st.subheader("Answer")
    st.success(result["answer"])
    if result.get("outcome"):
        st.caption(f"Outcome: {result['outcome']}")
    if result.get("matching_count") is not None:
        st.caption(f"Total matching results: {result['matching_count']}")
    timing = result.get("timing")
    if timing:
        st.caption(
            f"Timing: {timing['total_ms']:.1f} ms total "
            f"({timing['interpretation_ms']:.1f} ms interpretation, "
            f"{timing['execution_ms']:.1f} ms execution)."
        )
    for warning in result.get("warnings", []):
        st.warning(warning)
    _render_reference(result["reference_clock"])

    data = result.get("data")
    if data:
        if "requested_rule" in data:
            _render_anomaly_result(data)
        else:
            _render_analytics_result(data)
    else:
        st.info("No data query was run for this interpretation.")

    with st.expander("Interpreted request"):
        st.json(result["interpretation"])


def _render_analytics_result(data: dict[str, Any]) -> None:
    operation = data["operation"]
    if operation == "count":
        st.metric("Matching tickets", data["value"])
    elif operation == "aggregate":
        first, second, third = st.columns(3)
        first.metric("Result", _display_number(data.get("value")))
        second.metric("Matching tickets", data["matched_row_count"])
        third.metric("Contributing values", data["contributing_count"])
    elif operation == "grouped_aggregate":
        st.dataframe(data["rows"], width="stretch", hide_index=True)
        st.caption(
            f"Returned {data['returned_count']} of {data['matching_group_count']} "
            f"groups. Ties extended: {'yes' if data['ties_extended'] else 'no'}."
        )
    else:
        rows = [item["values"] for item in data["rows"]]
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.info("No ticket rows matched this question.")
        st.caption(
            f"Returned {data['returned_count']} of {data['matching_count']} matching "
            f"tickets from offset {data['offset']}."
        )
    _render_applied_range(data.get("applied_date_range"))


def _render_anomaly_tab(client: TicketAPI) -> None:
    st.subheader("Review explainable anomalies")
    rule = st.selectbox(
        "Rule",
        tuple(ANOMALY_RULE_LABELS),
        format_func=ANOMALY_RULE_LABELS.__getitem__,
    )
    period = st.selectbox(
        "Date period",
        tuple(PERIOD_LABELS),
        format_func=PERIOD_LABELS.__getitem__,
    )
    time_field = st.selectbox(
        "Date field",
        tuple(TIME_FIELD_LABELS),
        format_func=TIME_FIELD_LABELS.__getitem__,
        disabled=not period,
    )
    reference_mode, custom_reference = _reference_controls("anomaly")
    limit = st.slider("Rows per page", min_value=1, max_value=100, value=25)
    offset = st.number_input(
        "Offset",
        min_value=0,
        max_value=1_000_000,
        value=0,
        step=limit,
    )
    submitted = st.button(
        "Load anomalies", type="primary", key="submit_anomalies"
    )

    if submitted:
        params: dict[str, Any] = {
            "rule": rule,
            "period": period or None,
            "time_field": time_field or None,
            "reference_mode": reference_mode,
            "custom_reference": custom_reference,
            "limit": limit,
            "offset": offset,
        }
        try:
            st.session_state.anomaly_result = client.anomalies(params)
            st.session_state.pop("anomaly_error", None)
        except UIAPIError as exc:
            st.session_state.anomaly_error = str(exc)
            st.session_state.pop("anomaly_result", None)

    if error := st.session_state.get("anomaly_error"):
        st.error(error)
    result = st.session_state.get("anomaly_result")
    if result:
        _render_anomaly_result(result)


def _render_anomaly_result(result: dict[str, Any]) -> None:
    counts = result["rule_counts"]
    first, second, third, fourth = st.columns(4)
    first.metric("Unique flagged tickets", result["matching_ticket_count"])
    second.metric("Long resolution", counts["long_resolution"])
    third.metric("Overdue high priority", counts["overdue_high_priority"])
    fourth.metric(
        "Timing inconsistencies", counts["resolution_before_response"]
    )

    for warning in result.get("warnings", []):
        st.warning(warning)

    rows = []
    for ticket in result["tickets"]:
        row = {key: value for key, value in ticket.items() if key != "flags"}
        row["rules"] = ", ".join(flag["rule"] for flag in ticket["flags"])
        row["reasons"] = " | ".join(flag["reason"] for flag in ticket["flags"])
        rows.append(row)
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("No anomalies matched the selected filters.")
    st.caption(
        f"Returned {result['returned_count']} of {result['matching_ticket_count']} "
        f"flagged tickets from offset {result['offset']}."
    )
    baseline = result.get("long_resolution_baseline")
    if baseline:
        st.caption(
            "Long-resolution baseline: "
            f"Q1 {baseline['q1_hrs']:.2f} h, Q3 {baseline['q3_hrs']:.2f} h, "
            f"upper fence {baseline['upper_fence_hrs']:.2f} h "
            f"from {baseline['sample_size']} resolved tickets."
        )
    st.caption(
        f"Overdue high-priority threshold: {result['overdue_threshold_hrs']:.0f} hours."
    )
    st.caption(
        "Data-quality rule: flags records where reported resolution time is shorter "
        "than first-response time; source values are preserved."
    )
    _render_reference(result["reference_clock"])
    _render_applied_range(result.get("applied_date_range"))


def _reference_controls(prefix: str) -> tuple[str, str | None]:
    reference_mode = st.selectbox(
        "Reference time",
        tuple(REFERENCE_LABELS),
        format_func=REFERENCE_LABELS.__getitem__,
        key=f"{prefix}_reference_mode",
    )
    custom_reference = None
    if reference_mode == "custom":
        first, second = st.columns(2)
        custom_date = first.date_input(
            "Reference date",
            value=date(2024, 4, 5),
            key=f"{prefix}_reference_date",
        )
        custom_time = second.time_input(
            "Reference clock time",
            value=time(0, 0),
            key=f"{prefix}_reference_time",
        )
        custom_reference = datetime.combine(custom_date, custom_time).isoformat()
    return reference_mode, custom_reference


def _render_reference(reference: dict[str, Any]) -> None:
    st.caption(
        f"Reference: {reference['timestamp']} ({REFERENCE_LABELS[reference['mode']]})."
    )


def _render_applied_range(applied_range: dict[str, Any] | None) -> None:
    if applied_range:
        st.caption(
            f"Applied range: {applied_range['start']} to {applied_range['end']} "
            f"(end excluded; {applied_range['label']})."
        )


def _render_usage_guide() -> None:
    st.subheader("How results are produced")
    st.markdown(
        """
1. Local Qwen converts the question into a validated request.
2. Read-only SQLite and Python calculate the result.
3. The answer shows supporting rows, counts, date ranges, and warnings.

Use the **dataset reference** for reproducible assessment results. Current and custom
references change unresolved-ticket ages. The source is a snapshot, so historical
status cannot be reconstructed.
"""
    )


def _api_error_detail(response: httpx.Response) -> tuple[str, str]:
    try:
        payload = response.json()
    except ValueError:
        return (
            f"The API returned HTTP {response.status_code}.",
            "api_http_error",
        )
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = error.get("message")
        code = error.get("code")
        if isinstance(message, str) and isinstance(code, str):
            return message, code
    return f"The API returned HTTP {response.status_code}.", "api_http_error"


def _display_number(value: Any) -> str:
    if value is None:
        return "No value"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


if __name__ == "__main__":
    render_app()
