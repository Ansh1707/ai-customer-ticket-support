# Deterministic Analytics Execution

Step 9 implements the read-only analytics layer in `analytics.py`. It accepts only a
validated `AnalyticsRequest`; it does not accept SQL, table names, column names or
expressions from users or from the language model.

## Trust boundary

- SQL identifiers, derived expressions, aggregate functions and comparison operators
  are selected from fixed Python allowlists.
- Every filter value, date boundary, reference time, limit and offset is passed to
  SQLite as a named parameter.
- SQLite is opened with `mode=ro`, so the analytics path cannot change the snapshot.
- All filters use logical AND. Text containment uses a case-insensitive literal
  substring search, so `%`, `_`, quotes and SQL text have no wildcard or executable
  meaning.

## Calculation rules

- `resolved_at` is inferred as `created_at + resolution_time_hrs` only for resolved
  tickets.
- `unresolved_age_hrs` is calculated from creation to the visible reference time only
  for Open or Escalated tickets created by that reference.
- `resolution_elapsed_hrs` uses recorded resolution duration for resolved tickets and
  unresolved age for Open or Escalated tickets. This supports “not resolved within N
  hours” across both states.
- Counts return zero when nothing matches.
- Numeric aggregates ignore null metric values, following SQLite semantics. Results
  separately report matched rows and non-null contributors; an empty aggregate is
  `null` with zero contributors.
- Ticket lists append ticket ID as a stable tie-breaker when it is not explicitly
  sorted.
- Grouped queries compute every group before pagination. Result-ranked limits extend
  to include all groups tied at the boundary, then use the group value for stable
  ordering.
- Date ranges are half-open internally. The response carries the resolved range and
  reference-clock provenance.

## Supplied dataset verification

The executor was checked against independent calculations over the original CSV:

| Query | Verified result |
|---|---:|
| Open tickets | 111 |
| Critical tickets currently Open or Escalated | 31 |
| Average Technical customer rating | 3.7403846153846154 from 104 ratings |
| Critical tickets over 12 elapsed hours | 34 |
| Most inferred resolutions in April 1–5, 2024 | AGT-07 with 1 |
| Most inferred resolutions in March 2024 | AGT-01 with 16 |
| Lowest average customer rating by agent | AGT-08 with 3.48 from 25 ratings |

The April result is intentionally based on the dataset reference time of April 5,
2024 at 00:00. March is the `last_month` period from that reference.

## Automated verification

Tests cover counts, empty results, null-safe aggregation, contribution counts,
grouping, inferred resolution dates, relative ranges, elapsed-resolution logic,
stable list pagination, literal injection-shaped text, and tie preservation at a
ranking boundary. The complete suite passes with Ruff and bytecode compilation.
