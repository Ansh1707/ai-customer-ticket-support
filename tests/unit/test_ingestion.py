"""Tests for strict CSV validation without modifying the source dataset."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from ticket_support_ai.ingestion import (
    EXPECTED_COLUMNS,
    CSVValidationError,
    validate_csv,
)
from ticket_support_ai.schemas import TicketStatus, ValidationLevel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = PROJECT_ROOT / "support_tickets.csv"
EXPECTED_SHA256 = "812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff"


def valid_row(**overrides: str) -> dict[str, str]:
    row = {
        "ticket_id": "TKT-TEST",
        "created_at": "2024-01-03 09:12",
        "category": "Billing",
        "priority": "High",
        "status": "Resolved",
        "response_time_hrs": "0.5",
        "resolution_time_hrs": "2.3",
        "agent_id": "AGT-04",
        "customer_rating": "4",
        "issue_summary": "Incorrect charge on invoice",
    }
    row.update(overrides)
    return row


def write_csv(path: Path, rows: list[dict[str, str]], headers=EXPECTED_COLUMNS) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def issue_codes(error: CSVValidationError) -> set[str]:
    return {issue.code for issue in error.errors}


def test_supplied_dataset_validates_without_mutation() -> None:
    before = SOURCE_CSV.read_bytes()

    result = validate_csv(SOURCE_CSV)

    assert result.row_count == 500
    assert len(result.tickets) == 500
    assert len({ticket.ticket_id for ticket in result.tickets}) == 500
    assert result.source_sha256 == EXPECTED_SHA256
    assert len(result.warnings) == 28
    assert {warning.code for warning in result.warnings} == {
        "resolution_before_response"
    }
    assert all(warning.level is ValidationLevel.WARNING for warning in result.warnings)
    assert sum(ticket.status is TicketStatus.RESOLVED for ticket in result.tickets) == 327
    assert SOURCE_CSV.read_bytes() == before


@pytest.mark.parametrize(
    ("headers", "expected_code"),
    [
        (EXPECTED_COLUMNS[:-1], "missing_columns"),
        ((*EXPECTED_COLUMNS, "extra_column"), "unexpected_columns"),
        ((*EXPECTED_COLUMNS[:-1], "ticket_id"), "duplicate_columns"),
    ],
)
def test_rejects_invalid_headers(
    tmp_path: Path, headers: tuple[str, ...], expected_code: str
) -> None:
    path = tmp_path / "bad-header.csv"
    write_csv(path, [], headers=headers)

    with pytest.raises(CSVValidationError) as captured:
        validate_csv(path)

    assert expected_code in issue_codes(captured.value)


def test_rejects_duplicate_ticket_ids(tmp_path: Path) -> None:
    path = tmp_path / "duplicates.csv"
    write_csv(path, [valid_row(), valid_row()])

    with pytest.raises(CSVValidationError) as captured:
        validate_csv(path)

    issue = next(
        issue for issue in captured.value.errors if issue.code == "duplicate_ticket_id"
    )
    assert issue.row_number == 3
    assert "row 2" in issue.message


@pytest.mark.parametrize(
    ("overrides", "expected_code", "expected_field"),
    [
        ({"ticket_id": ""}, "missing_value", "ticket_id"),
        ({"agent_id": ""}, "missing_value", "agent_id"),
        ({"issue_summary": ""}, "missing_value", "issue_summary"),
        ({"created_at": "2024/01/03"}, "invalid_datetime", "created_at"),
        ({"category": "Sales"}, "invalid_enum", "category"),
        ({"priority": "Urgent"}, "invalid_enum", "priority"),
        ({"status": "Closed"}, "invalid_enum", "status"),
        ({"response_time_hrs": ""}, "missing_value", "response_time_hrs"),
        ({"response_time_hrs": "fast"}, "invalid_number", "response_time_hrs"),
        ({"response_time_hrs": "nan"}, "invalid_number", "response_time_hrs"),
        ({"response_time_hrs": "1e999"}, "non_finite_number", "response_time_hrs"),
        ({"resolution_time_hrs": "-1"}, "negative_number", "resolution_time_hrs"),
        ({"customer_rating": "3.5"}, "invalid_rating", "customer_rating"),
        ({"customer_rating": "6"}, "invalid_rating", "customer_rating"),
    ],
)
def test_rejects_invalid_field_values(
    tmp_path: Path,
    overrides: dict[str, str],
    expected_code: str,
    expected_field: str,
) -> None:
    path = tmp_path / "invalid-value.csv"
    write_csv(path, [valid_row(**overrides)])

    with pytest.raises(CSVValidationError) as captured:
        validate_csv(path)

    assert any(
        issue.code == expected_code and issue.field == expected_field
        for issue in captured.value.errors
    )


@pytest.mark.parametrize(
    ("overrides", "expected_codes"),
    [
        (
            {"resolution_time_hrs": "", "customer_rating": ""},
            {
                "resolved_missing_resolution_time",
                "resolved_missing_customer_rating",
            },
        ),
        (
            {"status": "Open"},
            {"unresolved_has_resolution_time", "unresolved_has_customer_rating"},
        ),
        (
            {
                "status": "Escalated",
                "resolution_time_hrs": "",
                "customer_rating": "",
            },
            set(),
        ),
    ],
)
def test_enforces_status_dependent_nulls(
    tmp_path: Path, overrides: dict[str, str], expected_codes: set[str]
) -> None:
    path = tmp_path / "status-nulls.csv"
    write_csv(path, [valid_row(**overrides)])

    if not expected_codes:
        assert validate_csv(path).row_count == 1
        return

    with pytest.raises(CSVValidationError) as captured:
        validate_csv(path)
    assert expected_codes <= issue_codes(captured.value)


def test_reports_resolution_before_response_as_warning(tmp_path: Path) -> None:
    path = tmp_path / "warning.csv"
    write_csv(
        path,
        [valid_row(response_time_hrs="4.0", resolution_time_hrs="2.0")],
    )

    result = validate_csv(path)

    assert result.row_count == 1
    assert [warning.code for warning in result.warnings] == [
        "resolution_before_response"
    ]
    assert result.tickets[0].response_time_hrs == 4.0
    assert result.tickets[0].resolution_time_hrs == 2.0


def test_rejects_row_width_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "short-row.csv"
    path.write_text(
        ",".join(EXPECTED_COLUMNS) + "\nTKT-001,2024-01-03 09:12\n",
        encoding="utf-8",
    )

    with pytest.raises(CSVValidationError) as captured:
        validate_csv(path)

    assert "row_width_mismatch" in issue_codes(captured.value)


def test_rejects_empty_missing_and_non_utf8_files(tmp_path: Path) -> None:
    empty_path = tmp_path / "empty.csv"
    empty_path.write_text("", encoding="utf-8")
    binary_path = tmp_path / "binary.csv"
    binary_path.write_bytes(b"\xff\xfe\x00")

    cases = [
        (empty_path, "empty_file"),
        (tmp_path / "missing.csv", "file_not_found"),
        (binary_path, "invalid_encoding"),
    ]
    for path, expected_code in cases:
        with pytest.raises(CSVValidationError) as captured:
            validate_csv(path)
        assert expected_code in issue_codes(captured.value)


def test_rejects_malformed_csv_syntax(tmp_path: Path) -> None:
    path = tmp_path / "malformed.csv"
    path.write_text(
        ",".join(EXPECTED_COLUMNS) + '\n"unterminated',
        encoding="utf-8",
    )

    with pytest.raises(CSVValidationError) as captured:
        validate_csv(path)

    assert "malformed_csv" in issue_codes(captured.value)


def test_accumulates_multiple_row_errors(tmp_path: Path) -> None:
    path = tmp_path / "several-errors.csv"
    write_csv(
        path,
        [
            valid_row(ticket_id="TKT-A", category="Sales"),
            valid_row(ticket_id="TKT-B", priority="Urgent"),
        ],
    )

    with pytest.raises(CSVValidationError) as captured:
        validate_csv(path)

    assert len(captured.value.errors) == 2
    assert {issue.row_number for issue in captured.value.errors} == {2, 3}
