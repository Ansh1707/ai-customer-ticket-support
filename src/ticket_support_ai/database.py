"""Transactional SQLite storage for validated support-ticket snapshots."""

from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from ticket_support_ai.ingestion import DATETIME_FORMAT, validate_csv
from ticket_support_ai.schemas import IngestionResult, TicketRecord

SCHEMA_VERSION = 1
DEFAULT_DATABASE_PATH = Path("data/runtime/support_tickets.db")

_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL,
    category TEXT NOT NULL
        CHECK (category IN ('Billing', 'Technical', 'General')),
    priority TEXT NOT NULL
        CHECK (priority IN ('Low', 'Medium', 'High', 'Critical')),
    status TEXT NOT NULL
        CHECK (status IN ('Open', 'Resolved', 'Escalated')),
    response_time_hrs REAL NOT NULL
        CHECK (response_time_hrs >= 0),
    resolution_time_hrs REAL
        CHECK (resolution_time_hrs IS NULL OR resolution_time_hrs >= 0),
    agent_id TEXT NOT NULL CHECK (length(trim(agent_id)) > 0),
    customer_rating INTEGER
        CHECK (customer_rating IS NULL OR customer_rating BETWEEN 1 AND 5),
    issue_summary TEXT NOT NULL CHECK (length(trim(issue_summary)) > 0),
    CHECK (
        (status = 'Resolved'
            AND resolution_time_hrs IS NOT NULL
            AND customer_rating IS NOT NULL)
        OR
        (status IN ('Open', 'Escalated')
            AND resolution_time_hrs IS NULL
            AND customer_rating IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_tickets_created_at
    ON tickets(created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_status_priority
    ON tickets(status, priority);
CREATE INDEX IF NOT EXISTS idx_tickets_category
    ON tickets(category);
CREATE INDEX IF NOT EXISTS idx_tickets_agent_id
    ON tickets(agent_id);

CREATE TABLE IF NOT EXISTS ingestion_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version INTEGER NOT NULL,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    warning_count INTEGER NOT NULL CHECK (warning_count >= 0),
    ingested_at TEXT NOT NULL
);

PRAGMA user_version = {SCHEMA_VERSION};
"""

_INSERT_TICKET_SQL = """
INSERT INTO tickets (
    ticket_id,
    created_at,
    category,
    priority,
    status,
    response_time_hrs,
    resolution_time_hrs,
    agent_id,
    customer_rating,
    issue_summary
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_UPSERT_METADATA_SQL = """
INSERT INTO ingestion_metadata (
    singleton,
    schema_version,
    source_path,
    source_sha256,
    row_count,
    warning_count,
    ingested_at
) VALUES (1, ?, ?, ?, ?, ?, ?)
ON CONFLICT(singleton) DO UPDATE SET
    schema_version = excluded.schema_version,
    source_path = excluded.source_path,
    source_sha256 = excluded.source_sha256,
    row_count = excluded.row_count,
    warning_count = excluded.warning_count,
    ingested_at = excluded.ingested_at
"""


@contextmanager
def database_connection(
    database_path: str | Path,
    *,
    read_only: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Open a configured SQLite connection and always close it."""

    path = Path(database_path).expanduser().resolve()
    if read_only:
        if not path.is_file():
            raise FileNotFoundError(f"SQLite database does not exist: {path}")
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        yield connection
    finally:
        connection.close()


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create the version-one schema or reject an unsupported database."""

    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version not in {0, SCHEMA_VERSION}:
        raise RuntimeError(
            f"Unsupported database schema version {current_version}; "
            f"expected 0 or {SCHEMA_VERSION}."
        )
    with connection:
        connection.executescript(_SCHEMA_SQL)


def ingest_csv_snapshot(
    source_path: str | Path,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> IngestionResult:
    """Validate and atomically store one complete CSV snapshot.

    A matching checksum and row count reuse the existing snapshot. A changed
    source replaces all tickets and metadata in one transaction, so an error
    cannot leave a partially refreshed database.
    """

    validated = validate_csv(source_path)
    resolved_database_path = Path(database_path).expanduser().resolve()

    with database_connection(resolved_database_path) as connection:
        initialize_database(connection)
        existing = _read_metadata(connection)
        stored_count = int(connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0])

        if (
            existing is not None
            and existing.source_sha256 == validated.source_sha256
            and existing.row_count == validated.row_count
            and stored_count == validated.row_count
        ):
            return existing.model_copy(update={"reused_existing": True})

        ingested_at = datetime.now(UTC).replace(microsecond=0)
        with connection:
            connection.execute("DELETE FROM tickets")
            connection.executemany(
                _INSERT_TICKET_SQL,
                (_ticket_parameters(ticket) for ticket in validated.tickets),
            )
            inserted_count = int(
                connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
            )
            if inserted_count != validated.row_count:
                raise RuntimeError(
                    "SQLite refresh row-count mismatch: "
                    f"expected {validated.row_count}, inserted {inserted_count}."
                )
            connection.execute(
                _UPSERT_METADATA_SQL,
                (
                    SCHEMA_VERSION,
                    str(validated.source_path),
                    validated.source_sha256,
                    validated.row_count,
                    len(validated.warnings),
                    ingested_at.isoformat(),
                ),
            )

        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")

    return IngestionResult(
        database_path=resolved_database_path,
        source_path=validated.source_path,
        source_sha256=validated.source_sha256,
        row_count=validated.row_count,
        warning_count=len(validated.warnings),
        ingested_at=ingested_at,
        reused_existing=False,
    )


def read_ingestion_metadata(database_path: str | Path) -> IngestionResult:
    """Read the persisted ingestion metadata from an initialized database."""

    resolved_database_path = Path(database_path).expanduser().resolve()
    with database_connection(resolved_database_path, read_only=True) as connection:
        metadata = _read_metadata(connection)
    if metadata is None:
        raise RuntimeError("SQLite database has no ingestion metadata.")
    return metadata


def read_tickets(database_path: str | Path) -> tuple[TicketRecord, ...]:
    """Read the validated ticket snapshot through a read-only connection."""

    with database_connection(database_path, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT
                ticket_id,
                created_at,
                category,
                priority,
                status,
                response_time_hrs,
                resolution_time_hrs,
                agent_id,
                customer_rating,
                issue_summary
            FROM tickets
            ORDER BY ticket_id
            """
        ).fetchall()
    return tuple(
        TicketRecord(
            ticket_id=row["ticket_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            category=row["category"],
            priority=row["priority"],
            status=row["status"],
            response_time_hrs=row["response_time_hrs"],
            resolution_time_hrs=row["resolution_time_hrs"],
            agent_id=row["agent_id"],
            customer_rating=row["customer_rating"],
            issue_summary=row["issue_summary"],
        )
        for row in rows
    )


def _read_metadata(connection: sqlite3.Connection) -> IngestionResult | None:
    row = connection.execute(
        """
        SELECT source_path, source_sha256, row_count, warning_count, ingested_at
        FROM ingestion_metadata
        WHERE singleton = 1
        """
    ).fetchone()
    if row is None:
        return None
    database_row = connection.execute("PRAGMA database_list").fetchone()
    database_path = Path(database_row[2]).resolve()
    return IngestionResult(
        database_path=database_path,
        source_path=Path(row["source_path"]),
        source_sha256=row["source_sha256"],
        row_count=row["row_count"],
        warning_count=row["warning_count"],
        ingested_at=datetime.fromisoformat(row["ingested_at"]),
        reused_existing=False,
    )


def _ticket_parameters(ticket: TicketRecord) -> tuple[object, ...]:
    return (
        ticket.ticket_id,
        ticket.created_at.strftime(DATETIME_FORMAT),
        ticket.category.value,
        ticket.priority.value,
        ticket.status.value,
        ticket.response_time_hrs,
        ticket.resolution_time_hrs,
        ticket.agent_id,
        ticket.customer_rating,
        ticket.issue_summary,
    )


def _format_result(result: IngestionResult) -> str:
    action = "reused" if result.reused_existing else "refreshed"
    return (
        f"SQLite snapshot {action}: {result.row_count} ticket(s), "
        f"{result.warning_count} source warning(s), "
        f"database={result.database_path}, SHA-256={result.source_sha256}"
    )


def main() -> int:
    """Load a validated CSV snapshot into SQLite."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"SQLite output path (default: {DEFAULT_DATABASE_PATH})",
    )
    args = parser.parse_args()
    result = ingest_csv_snapshot(args.csv_path, args.database)
    print(_format_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
