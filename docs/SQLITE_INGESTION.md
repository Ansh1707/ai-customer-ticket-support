# SQLite Ingestion

Step 6 stores a complete validated CSV snapshot in SQLite. The database is generated runtime state and is intentionally excluded from Git.

## Run ingestion

From the project root:

```bash
PYTHONPATH=src .venv/bin/python -m ticket_support_ai.database \
  support_tickets.csv \
  --database data/runtime/support_tickets.db
```

The first run reports `refreshed`. A later run with the same source checksum and row count reports `reused` and does not append or replace rows.

## Transaction behavior

1. Validate the complete CSV before creating or changing the database.
2. Create or verify schema version 1.
3. Reuse an existing snapshot when checksum, metadata row count and stored row count all match.
4. For a changed valid source, delete the old snapshot, insert every new ticket and update metadata inside one transaction.
5. Confirm the inserted row count before committing.
6. Run SQLite `quick_check` after a committed refresh.

If an insert or metadata update fails, SQLite rolls back the deletion and every partial insert. The previous valid snapshot and its metadata remain available.

## Database schema

The `tickets` table contains the ten source columns. SQLite types are `TEXT`, `REAL` and `INTEGER` according to the assessment schema. The database adds constraints for:

- unique non-null ticket IDs;
- documented category, priority and status values;
- nonnegative durations;
- ratings from 1 through 5;
- nonblank agent IDs and issue summaries;
- resolved versus unresolved null rules.

Indexes support time, status and priority, category, and agent queries. Application analytics should open SQLite in read-only mode.

The singleton `ingestion_metadata` table records:

- schema version;
- absolute source path;
- source SHA-256 checksum;
- imported row count;
- validation warning count;
- UTC ingestion timestamp.

## Verified result

| Check | Result |
|---|---:|
| Database schema version | 1 |
| Stored tickets | 500 |
| Unique ticket IDs | 500 |
| Resolved | 327 |
| Open | 111 |
| Escalated | 62 |
| Invalid status/null combinations | 0 |
| Recorded source warnings | 28 |
| SQLite `quick_check` | `ok` |
| Repeated source ingestion | Existing snapshot reused |

Automated tests also verify full replacement for changed sources, rollback after a simulated mid-refresh failure, database constraints, read-only connections, and prevention of database creation when CSV validation fails.
