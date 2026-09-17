# Deterministic Verification

Steps 23 and 24 verify calculations and boundary behavior without calling Qwen. The
primary regression test reads the unchanged CSV with Python's standard `csv` module
and calculates its facts independently of the ingestion, SQLite, analytics, date, and
anomaly modules.

## Supplied-file regression facts

The independent test first checks the source SHA-256
`812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff`, then verifies:

| Calculation | Verified result |
|---|---:|
| Open tickets | 111 |
| Unresolved tickets | 173 |
| Unresolved Critical tickets | 31 |
| Technical rating average | 3.7403846153846154 from 104 ratings; displays as 3.74 |
| Lowest agent rating | AGT-08, 3.48 from 25 ratings |
| Most inferred March resolutions | AGT-01, 16 tickets |
| Long-resolution IQR findings | 21; Q1 6.15, Q3 22.95, upper fence 48.15 hours |
| Resolution-before-response inconsistencies | 28 |
| Overdue unresolved High/Critical tickets | 80 |
| Critical tickets over 12 elapsed hours | 34 |

These values are assertions in `tests/regression/test_dataset_facts.py`; they are not
used by application runtime code. Application-level tests separately submit typed
requests through the real SQLite executor and anomaly engine.

## Boundary-condition matrix

| Required boundary | Automated evidence |
|---|---|
| Missing files and headers | Missing, empty, encoding, missing/extra/duplicate header tests |
| Duplicate identifiers | Duplicate ticket ID with source row evidence |
| Invalid numeric values | Text, NaN, infinity, negative duration, fractional/out-of-range rating tests |
| Expected and unexpected nulls | Resolved-required and unresolved-forbidden duration/rating tests |
| Empty query results | Zero count and empty aggregate with zero contributions |
| No available ratings | 173 unresolved matches, zero rating contributors, null average |
| Exactly 12 hours | Resolved and unresolved values at 12 excluded; 12.01 and 12h01m included |
| Exactly 24 hours | Exactly 24 excluded; 24h00m01s included |
| Created after reference | Future unresolved ticket has no age and is excluded |
| Month and week boundaries | Monday/month starts, prior periods, empty exact-boundary periods, half-open ends |
| Ranking ties | All groups tied at the requested boundary are returned |
| Multiple anomaly reasons | One unique ticket contains both long-duration and timing-inconsistency flags |
| Small anomaly baseline | Three durations return an insufficient-baseline warning and no flags |
| Constant anomaly baseline | Zero IQR returns an insufficient-variation warning and no flags |
| Repeated ingestion | Matching source is reused at 500 rows without appending duplicates |

The test suite also verifies stable pagination, transactional rollback, replacement of
changed snapshots, read-only analytics connections, SQL-injection-shaped literals,
and source preservation.

## Commands

Run only the deterministic acceptance coverage:

```bash
python -m pytest -q \
  tests/regression/test_dataset_facts.py \
  tests/unit/test_analytics.py \
  tests/unit/test_anomalies.py \
  tests/unit/test_dates.py \
  tests/unit/test_ingestion.py \
  tests/unit/test_database.py
```

Run the complete non-live suite with `python -m pytest -q`. Live Qwen tests remain
separate because Steps 23 and 24 are intended to isolate deterministic correctness.
