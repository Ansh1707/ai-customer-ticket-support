"""Strict validation for the supplied customer-support CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from ticket_support_ai.schemas import (
    TicketCategory,
    TicketPriority,
    TicketRecord,
    TicketStatus,
    ValidatedCSV,
    ValidationIssue,
    ValidationLevel,
)

EXPECTED_COLUMNS = (
    "ticket_id",
    "created_at",
    "category",
    "priority",
    "status",
    "response_time_hrs",
    "resolution_time_hrs",
    "agent_id",
    "customer_rating",
    "issue_summary",
)

DATETIME_FORMAT = "%Y-%m-%d %H:%M"
_NUMBER_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")
EnumT = TypeVar("EnumT", TicketCategory, TicketPriority, TicketStatus)


class CSVValidationError(ValueError):
    """Raised when a CSV cannot be safely accepted for ingestion."""

    def __init__(
        self,
        errors: tuple[ValidationIssue, ...],
        warnings: tuple[ValidationIssue, ...] = (),
    ) -> None:
        self.errors = errors
        self.warnings = warnings
        preview = "; ".join(_format_issue(issue) for issue in errors[:5])
        suffix = "" if len(errors) <= 5 else f"; plus {len(errors) - 5} more"
        super().__init__(
            f"CSV validation failed with {len(errors)} error(s): {preview}{suffix}"
        )


def validate_csv(source: str | Path) -> ValidatedCSV:
    """Validate a support-ticket CSV and return immutable typed records.

    Structural or row-level errors raise :class:`CSVValidationError`. Cross-field
    timing inconsistencies are retained as warnings so source data is never
    silently changed or discarded.
    """

    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise CSVValidationError(
            (
                _issue(
                    ValidationLevel.ERROR,
                    "file_not_found",
                    f"CSV file does not exist: {source_path}",
                ),
            )
        )

    source_sha256 = _sha256(source_path)
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    tickets: list[TicketRecord] = []
    seen_ticket_ids: dict[str, int] = {}

    try:
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                raise CSVValidationError(
                    (
                        _issue(
                            ValidationLevel.ERROR,
                            "empty_file",
                            "CSV file is empty and has no header row.",
                            row_number=1,
                        ),
                    )
                ) from None

            header_errors = _validate_header(header)
            if header_errors:
                raise CSVValidationError(tuple(header_errors))

            positions = {name: header.index(name) for name in EXPECTED_COLUMNS}
            for row_number, row in enumerate(reader, start=2):
                if len(row) != len(header):
                    errors.append(
                        _issue(
                            ValidationLevel.ERROR,
                            "row_width_mismatch",
                            f"Expected {len(header)} fields but found {len(row)}.",
                            row_number=row_number,
                        )
                    )
                    continue

                values = {name: row[index] for name, index in positions.items()}
                row_error_count = len(errors)
                ticket_id = _required_text(values, "ticket_id", row_number, errors)
                agent_id = _required_text(values, "agent_id", row_number, errors)
                issue_summary = _required_text(
                    values, "issue_summary", row_number, errors
                )

                if ticket_id:
                    first_row = seen_ticket_ids.get(ticket_id)
                    if first_row is not None:
                        errors.append(
                            _issue(
                                ValidationLevel.ERROR,
                                "duplicate_ticket_id",
                                f"Ticket ID duplicates row {first_row}.",
                                row_number=row_number,
                                field="ticket_id",
                                ticket_id=ticket_id,
                            )
                        )
                    else:
                        seen_ticket_ids[ticket_id] = row_number

                created_at = _parse_datetime(
                    values["created_at"], row_number, ticket_id, errors
                )
                category = _parse_enum(
                    values["category"],
                    TicketCategory,
                    "category",
                    row_number,
                    ticket_id,
                    errors,
                )
                priority = _parse_enum(
                    values["priority"],
                    TicketPriority,
                    "priority",
                    row_number,
                    ticket_id,
                    errors,
                )
                status = _parse_enum(
                    values["status"],
                    TicketStatus,
                    "status",
                    row_number,
                    ticket_id,
                    errors,
                )
                response_time = _parse_float(
                    values["response_time_hrs"],
                    "response_time_hrs",
                    row_number,
                    ticket_id,
                    errors,
                    required=True,
                )
                resolution_time = _parse_float(
                    values["resolution_time_hrs"],
                    "resolution_time_hrs",
                    row_number,
                    ticket_id,
                    errors,
                    required=False,
                )
                customer_rating = _parse_rating(
                    values["customer_rating"], row_number, ticket_id, errors
                )

                _validate_status_nulls(
                    status,
                    values["resolution_time_hrs"],
                    values["customer_rating"],
                    row_number,
                    ticket_id,
                    errors,
                )

                if (
                    response_time is not None
                    and resolution_time is not None
                    and resolution_time < response_time
                ):
                    warnings.append(
                        _issue(
                            ValidationLevel.WARNING,
                            "resolution_before_response",
                            "Resolution time is shorter than first-response time; "
                            "the source values were retained unchanged.",
                            row_number=row_number,
                            field="resolution_time_hrs",
                            ticket_id=ticket_id,
                        )
                    )

                if len(errors) == row_error_count:
                    tickets.append(
                        TicketRecord(
                            ticket_id=ticket_id,
                            created_at=created_at,
                            category=category,
                            priority=priority,
                            status=status,
                            response_time_hrs=response_time,
                            resolution_time_hrs=resolution_time,
                            agent_id=agent_id,
                            customer_rating=customer_rating,
                            issue_summary=issue_summary,
                        )
                    )
    except UnicodeDecodeError as exc:
        raise CSVValidationError(
            (
                _issue(
                    ValidationLevel.ERROR,
                    "invalid_encoding",
                    f"File is not valid UTF-8 near byte {exc.start}.",
                ),
            )
        ) from exc
    except csv.Error as exc:
        raise CSVValidationError(
            (
                _issue(
                    ValidationLevel.ERROR,
                    "malformed_csv",
                    f"CSV syntax error: {exc}",
                ),
            )
        ) from exc

    if errors:
        raise CSVValidationError(tuple(errors), tuple(warnings))

    return ValidatedCSV(
        source_path=source_path,
        source_sha256=source_sha256,
        row_count=len(tickets),
        tickets=tuple(tickets),
        warnings=tuple(warnings),
    )


def _validate_header(header: list[str]) -> list[ValidationIssue]:
    errors: list[ValidationIssue] = []
    duplicate_columns = sorted({name for name in header if header.count(name) > 1})
    missing_columns = sorted(set(EXPECTED_COLUMNS) - set(header))
    unexpected_columns = sorted(set(header) - set(EXPECTED_COLUMNS))

    if duplicate_columns:
        errors.append(
            _issue(
                ValidationLevel.ERROR,
                "duplicate_columns",
                f"Duplicate column name(s): {', '.join(duplicate_columns)}.",
                row_number=1,
            )
        )
    if missing_columns:
        errors.append(
            _issue(
                ValidationLevel.ERROR,
                "missing_columns",
                f"Missing required column(s): {', '.join(missing_columns)}.",
                row_number=1,
            )
        )
    if unexpected_columns:
        errors.append(
            _issue(
                ValidationLevel.ERROR,
                "unexpected_columns",
                f"Unexpected column(s): {', '.join(unexpected_columns)}.",
                row_number=1,
            )
        )
    return errors


def _required_text(
    values: dict[str, str],
    field: str,
    row_number: int,
    errors: list[ValidationIssue],
) -> str | None:
    value = values[field]
    if not value.strip():
        errors.append(
            _issue(
                ValidationLevel.ERROR,
                "missing_value",
                "Required value is blank.",
                row_number=row_number,
                field=field,
                ticket_id=values.get("ticket_id") or None,
            )
        )
        return None
    return value


def _parse_datetime(
    value: str,
    row_number: int,
    ticket_id: str | None,
    errors: list[ValidationIssue],
) -> datetime | None:
    try:
        # The assessment defines local-looking timestamps but provides no timezone.
        parsed = datetime.strptime(value, DATETIME_FORMAT)  # noqa: DTZ007
    except ValueError:
        parsed = None
    if parsed is None or parsed.strftime(DATETIME_FORMAT) != value:
        errors.append(
            _issue(
                ValidationLevel.ERROR,
                "invalid_datetime",
                f"Expected exact format {DATETIME_FORMAT!r}; found {value!r}.",
                row_number=row_number,
                field="created_at",
                ticket_id=ticket_id,
            )
        )
        return None
    return parsed


def _parse_enum(
    value: str,
    enum_type: Callable[[str], EnumT],
    field: str,
    row_number: int,
    ticket_id: str | None,
    errors: list[ValidationIssue],
) -> EnumT | None:
    try:
        return enum_type(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_type)  # type: ignore[attr-defined]
        errors.append(
            _issue(
                ValidationLevel.ERROR,
                "invalid_enum",
                f"Expected one of [{allowed}]; found {value!r}.",
                row_number=row_number,
                field=field,
                ticket_id=ticket_id,
            )
        )
        return None


def _parse_float(
    value: str,
    field: str,
    row_number: int,
    ticket_id: str | None,
    errors: list[ValidationIssue],
    *,
    required: bool,
) -> float | None:
    if not value.strip():
        if required:
            errors.append(
                _issue(
                    ValidationLevel.ERROR,
                    "missing_value",
                    "Required numeric value is blank.",
                    row_number=row_number,
                    field=field,
                    ticket_id=ticket_id,
                )
            )
        return None

    if not _NUMBER_PATTERN.fullmatch(value):
        errors.append(
            _issue(
                ValidationLevel.ERROR,
                "invalid_number",
                f"Expected a decimal number; found {value!r}.",
                row_number=row_number,
                field=field,
                ticket_id=ticket_id,
            )
        )
        return None

    parsed = float(value)
    if not math.isfinite(parsed):
        errors.append(
            _issue(
                ValidationLevel.ERROR,
                "non_finite_number",
                "Numeric value must be finite.",
                row_number=row_number,
                field=field,
                ticket_id=ticket_id,
            )
        )
        return None
    if parsed < 0:
        errors.append(
            _issue(
                ValidationLevel.ERROR,
                "negative_number",
                "Duration cannot be negative.",
                row_number=row_number,
                field=field,
                ticket_id=ticket_id,
            )
        )
        return None
    return parsed


def _parse_rating(
    value: str,
    row_number: int,
    ticket_id: str | None,
    errors: list[ValidationIssue],
) -> int | None:
    if not value.strip():
        return None
    if not _INTEGER_PATTERN.fullmatch(value):
        errors.append(
            _issue(
                ValidationLevel.ERROR,
                "invalid_rating",
                f"Customer rating must be an integer from 1 to 5; found {value!r}.",
                row_number=row_number,
                field="customer_rating",
                ticket_id=ticket_id,
            )
        )
        return None
    rating = int(value)
    if rating < 1 or rating > 5:
        errors.append(
            _issue(
                ValidationLevel.ERROR,
                "invalid_rating",
                f"Customer rating must be from 1 to 5; found {rating}.",
                row_number=row_number,
                field="customer_rating",
                ticket_id=ticket_id,
            )
        )
        return None
    return rating


def _validate_status_nulls(
    status: TicketStatus | None,
    resolution_time_raw: str,
    customer_rating_raw: str,
    row_number: int,
    ticket_id: str | None,
    errors: list[ValidationIssue],
) -> None:
    if status is TicketStatus.RESOLVED:
        if not resolution_time_raw.strip():
            errors.append(
                _issue(
                    ValidationLevel.ERROR,
                    "resolved_missing_resolution_time",
                    "Resolved ticket must have a resolution time.",
                    row_number=row_number,
                    field="resolution_time_hrs",
                    ticket_id=ticket_id,
                )
            )
        if not customer_rating_raw.strip():
            errors.append(
                _issue(
                    ValidationLevel.ERROR,
                    "resolved_missing_customer_rating",
                    "Resolved ticket must have a customer rating.",
                    row_number=row_number,
                    field="customer_rating",
                    ticket_id=ticket_id,
                )
            )
    elif status in {TicketStatus.OPEN, TicketStatus.ESCALATED}:
        if resolution_time_raw.strip():
            errors.append(
                _issue(
                    ValidationLevel.ERROR,
                    "unresolved_has_resolution_time",
                    "Open or Escalated ticket must not have a resolution time.",
                    row_number=row_number,
                    field="resolution_time_hrs",
                    ticket_id=ticket_id,
                )
            )
        if customer_rating_raw.strip():
            errors.append(
                _issue(
                    ValidationLevel.ERROR,
                    "unresolved_has_customer_rating",
                    "Open or Escalated ticket must not have a customer rating.",
                    row_number=row_number,
                    field="customer_rating",
                    ticket_id=ticket_id,
                )
            )


def _issue(
    level: ValidationLevel,
    code: str,
    message: str,
    *,
    row_number: int | None = None,
    field: str | None = None,
    ticket_id: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        level=level,
        code=code,
        message=message,
        row_number=row_number,
        field=field,
        ticket_id=ticket_id,
    )


def _format_issue(issue: ValidationIssue) -> str:
    location = []
    if issue.row_number is not None:
        location.append(f"row {issue.row_number}")
    if issue.field is not None:
        location.append(f"field {issue.field}")
    prefix = ", ".join(location)
    return f"{prefix}: {issue.message}" if prefix else issue.message


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    """Run validation as a small diagnostic command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()

    try:
        result = validate_csv(args.csv_path)
    except CSVValidationError as exc:
        print(str(exc))
        for issue in exc.errors:
            print(f"ERROR [{issue.code}] {_format_issue(issue)}")
        for issue in exc.warnings:
            print(f"WARNING [{issue.code}] {_format_issue(issue)}")
        return 1

    print(
        f"Validated {result.row_count} ticket(s); "
        f"{len(result.warnings)} warning(s); SHA-256 {result.source_sha256}"
    )
    for issue in result.warnings:
        print(f"WARNING [{issue.code}] {_format_issue(issue)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
