"""Tests for atomic and idempotent SQLite snapshot ingestion."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from ticket_support_ai.database import (
    SCHEMA_VERSION,
    database_connection,
    ingest_csv_snapshot,
    read_ingestion_metadata,
    read_tickets,
)
from ticket_support_ai.ingestion import EXPECTED_COLUMNS, CSVValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = PROJECT_ROOT / "support_tickets.csv"
EXPECTED_SHA256 = "812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff"


def valid_row(ticket_id: str, **overrides: str) -> dict[str, str]:
    row = {
        "ticket_id": ticket_id,
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


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_ingests_supplied_csv_with_schema_indexes_and_metadata(tmp_path: Path) -> None:
    database = tmp_path / "nested" / "tickets.db"

    result = ingest_csv_snapshot(SOURCE_CSV, database)

    assert result.database_path == database.resolve()
    assert result.source_sha256 == EXPECTED_SHA256
    assert result.row_count == 500
    assert result.warning_count == 28
    assert result.reused_existing is False
    assert result.ingested_at.utcoffset() is not None

    with database_connection(database, read_only=True) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 500
        assert (
            connection.execute(
                "SELECT COUNT(DISTINCT ticket_id) FROM tickets"
            ).fetchone()[0]
            == 500
        )
        columns = {
            row["name"]: row["type"]
            for row in connection.execute("PRAGMA table_info(tickets)")
        }
        assert columns == {
            "ticket_id": "TEXT",
            "created_at": "TEXT",
            "category": "TEXT",
            "priority": "TEXT",
            "status": "TEXT",
            "response_time_hrs": "REAL",
            "resolution_time_hrs": "REAL",
            "agent_id": "TEXT",
            "customer_rating": "INTEGER",
            "issue_summary": "TEXT",
        }
        indexes = {
            row["name"] for row in connection.execute("PRAGMA index_list(tickets)")
        }
        assert {
            "idx_tickets_created_at",
            "idx_tickets_status_priority",
            "idx_tickets_category",
            "idx_tickets_agent_id",
        } <= indexes

    persisted = read_ingestion_metadata(database)
    assert persisted.source_sha256 == result.source_sha256
    assert persisted.row_count == result.row_count
    assert persisted.warning_count == result.warning_count

    tickets = read_tickets(database)
    assert len(tickets) == 500
    assert tickets[0].ticket_id == "TKT-001"
    assert tickets[-1].ticket_id == "TKT-500"


def test_repeated_ingestion_reuses_matching_snapshot(tmp_path: Path) -> None:
    database = tmp_path / "tickets.db"

    first = ingest_csv_snapshot(SOURCE_CSV, database)
    second = ingest_csv_snapshot(SOURCE_CSV, database)

    assert first.reused_existing is False
    assert second.reused_existing is True
    assert second.ingested_at == first.ingested_at
    with database_connection(database, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 500


def test_changed_source_replaces_snapshot_instead_of_appending(tmp_path: Path) -> None:
    source = tmp_path / "tickets.csv"
    database = tmp_path / "tickets.db"
    write_csv(source, [valid_row("TKT-OLD")])
    ingest_csv_snapshot(source, database)

    write_csv(source, [valid_row("TKT-A"), valid_row("TKT-B")])
    result = ingest_csv_snapshot(source, database)

    assert result.reused_existing is False
    assert result.row_count == 2
    with database_connection(database, read_only=True) as connection:
        ids = {
            row["ticket_id"]
            for row in connection.execute("SELECT ticket_id FROM tickets")
        }
    assert ids == {"TKT-A", "TKT-B"}


def test_failed_refresh_rolls_back_tickets_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "tickets.csv"
    database = tmp_path / "tickets.db"
    write_csv(source, [valid_row("TKT-OLD")])
    before = ingest_csv_snapshot(source, database)

    with database_connection(database) as connection, connection:
        connection.execute(
            """
            CREATE TRIGGER reject_tkt_b
            BEFORE INSERT ON tickets
            WHEN NEW.ticket_id = 'TKT-B'
            BEGIN
                SELECT RAISE(ABORT, 'simulated insert failure');
            END
            """
        )

    write_csv(source, [valid_row("TKT-A"), valid_row("TKT-B")])
    with pytest.raises(sqlite3.IntegrityError, match="simulated insert failure"):
        ingest_csv_snapshot(source, database)

    with database_connection(database, read_only=True) as connection:
        rows = connection.execute("SELECT ticket_id FROM tickets").fetchall()
    after = read_ingestion_metadata(database)
    assert [row["ticket_id"] for row in rows] == ["TKT-OLD"]
    assert after.source_sha256 == before.source_sha256
    assert after.row_count == 1


def test_database_constraints_reject_invalid_direct_writes(tmp_path: Path) -> None:
    source = tmp_path / "tickets.csv"
    database = tmp_path / "tickets.db"
    write_csv(source, [valid_row("TKT-VALID")])
    ingest_csv_snapshot(source, database)

    with (
        database_connection(database) as connection,
        pytest.raises(sqlite3.IntegrityError),
        connection,
    ):
        connection.execute(
            """
            INSERT INTO tickets VALUES (
                'TKT-BAD', '2024-01-03 09:12', 'Billing', 'High', 'Open',
                0.5, 2.3, 'AGT-04', 4, 'Invalid unresolved record'
            )
            """
        )


def test_read_only_connection_rejects_writes(tmp_path: Path) -> None:
    source = tmp_path / "tickets.csv"
    database = tmp_path / "tickets.db"
    write_csv(source, [valid_row("TKT-VALID")])
    ingest_csv_snapshot(source, database)

    with (
        database_connection(database, read_only=True) as connection,
        pytest.raises(sqlite3.OperationalError, match="readonly"),
    ):
        connection.execute("DELETE FROM tickets")


def test_invalid_csv_does_not_create_database(tmp_path: Path) -> None:
    source = tmp_path / "invalid.csv"
    database = tmp_path / "nested" / "tickets.db"
    write_csv(source, [valid_row("TKT-BAD", category="Sales")])

    with pytest.raises(CSVValidationError):
        ingest_csv_snapshot(source, database)

    assert not database.exists()
