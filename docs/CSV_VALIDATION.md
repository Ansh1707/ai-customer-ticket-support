# CSV Validation

Step 5 implements strict validation for the supplied support-ticket dataset. Validation reads the source without modifying it and returns immutable typed records only when no blocking errors are present.

## Run the validator

From the project root with the virtual environment available:

```bash
PYTHONPATH=src .venv/bin/python -m ticket_support_ai.ingestion support_tickets.csv
```

A successful run reports the accepted row count, warning count and SHA-256 checksum. A failed run exits with status 1 and identifies each error by code, CSV row and field where applicable.

## Blocking validation rules

- The file must exist and decode as UTF-8. A UTF-8 byte-order mark is accepted.
- The header must contain each required column exactly once and no unexpected columns.
- Every data row must contain the same number of fields as the header.
- Ticket IDs, agent IDs and issue summaries must be nonblank.
- Ticket IDs must be unique.
- Creation timestamps must exactly match `YYYY-MM-DD HH:MM`.
- Category, priority and status values must match the documented values exactly.
- Response time is required. Duration values must be valid, finite and nonnegative.
- Customer ratings must be integers from 1 through 5 when present.
- Resolved tickets require resolution time and customer rating.
- Open and Escalated tickets require null resolution time and customer rating.

The source provides no timezone. Parsed timestamps therefore remain naive dataset-local values. Reference-clock and timezone policy will be implemented in the dedicated date step.

## Non-blocking warning

When a ticket's resolution duration is shorter than its first-response duration, validation emits `resolution_before_response`. It keeps the original values and accepts the row. The supplied file has 28 such warnings.

## Verified source result

| Check | Result |
|---|---:|
| Accepted rows | 500 |
| Unique ticket IDs | 500 |
| Blocking errors | 0 |
| Timing warnings | 28 |
| Resolved tickets | 327 |
| Source SHA-256 | `812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff` |

Automated tests cover the supplied file, file and encoding failures, header defects, malformed CSV, row-width mismatches, duplicate IDs, required text, timestamp and enum validation, numeric boundaries, rating validation, status-dependent nulls, warning preservation and accumulation of errors across rows.
