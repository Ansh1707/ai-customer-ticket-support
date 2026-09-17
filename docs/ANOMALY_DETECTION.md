# Deterministic Anomaly Detection

The anomaly engine implements three explainable rules in `anomalies.py`. The language
model may select a rule and date range later, but it does not calculate thresholds or
decide which records are anomalous.

## Long resolution rule

The baseline contains every resolved ticket with a recorded
`resolution_time_hrs`. Quartiles use linear type-7 interpolation, the default method
used by common analytical tools:

```text
IQR = Q3 - Q1
upper fence = Q3 + 1.5 × IQR
```

A resolved ticket is flagged only when its duration is strictly greater than the
upper fence. A value exactly on the fence is not anomalous. The full-snapshot baseline
is retained when a date filter is applied; the filter scopes reported candidates.
This prevents a small period, such as a partial week containing one resolution, from
producing an unstable local threshold.

At least four valid durations and a non-zero IQR are required. Otherwise the result
contains an explicit insufficient-variation warning and no long-resolution flags.

For the supplied snapshot:

| Statistic | Value |
|---|---:|
| Resolved baseline records | 327 |
| Q1 | 6.15 hours |
| Q3 | 22.95 hours |
| IQR | 16.80 hours |
| Multiplier | 1.5 |
| Upper fence | 48.15 hours |
| Flagged long resolutions | 21 |

## Overdue high-priority rule

A ticket is flagged when all of these conditions hold:

- its current status is Open or Escalated;
- its priority is High or Critical;
- it was created at or before the selected reference time; and
- its age at that reference is strictly greater than 24 hours.

Exactly 24 hours is not flagged. Future-created tickets are excluded. At the default
April 5, 2024 00:00 reference, the supplied snapshot contains 80 such tickets: 49 High
and 31 Critical.

## Source timing inconsistency rule

A resolved record is flagged when `resolution_time_hrs` is shorter than
`response_time_hrs`. Both reported values remain unchanged. The reason identifies the
record as an observed source-data inconsistency rather than a corrected measurement.
The supplied snapshot contains exactly 28 such records.

## Date filters

An optional time filter uses the shared half-open date-range implementation. The
filter's selected field is respected directly:

- `resolved_at` uses the inferred resolution timestamp and naturally excludes
  unresolved tickets;
- `created_at` uses ticket creation time.

For “anomalies in resolution times this week,” the request uses `resolved_at` and
`this_week`. The applied range is April 1, 2024 00:00 through April 5, 2024 00:00,
with the end excluded. Ticket `TKT-108`, resolved in 119.7 hours, is the one long
resolution anomaly in that range.

## Results and ordering

- Each ticket appears once even if future rules cause it to trigger more than one
  flag.
- Every flag includes its rule, observed hours, threshold, relevant event timestamp,
  and a human-readable reason.
- Results include unpaginated per-rule counts, unique matching-ticket count, reference
  clock, applied date range, baseline statistics, and pagination metadata.
- Findings are ordered by observed-to-threshold severity and then ticket ID, making
  pagination deterministic.
- SQLite is opened read-only. Detection operates on validated typed ticket records.

The supplied dataset has 21 long-resolution findings, 80 overdue high-priority
findings, and 28 source timing inconsistencies. These are 129 unique tickets; per-rule
counts are still returned separately so callers do not need to add them.

## Automated verification

Tests independently verify the supplied-data statistics and counts, the weekly sample
query, empty resolved populations, zero-IQR behavior, exact 24-hour and IQR boundaries,
future-ticket exclusion, unique findings, explanations, stable pagination, and counts
before pagination.
