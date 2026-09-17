# Analytics Request Contract

Step 8 defines the only structured requests that the natural-language interpreter may send to deterministic application code. The contract contains no SQL, Python, table names or arbitrary expressions.

## Supported intents

| Intent | Purpose |
|---|---|
| Analytics | Count, list, aggregate or group ticket data |
| Anomalies | Route to the deterministic anomaly engine |
| Clarification | Ask the user for a material missing choice |
| Unsupported | Explain that the request is outside the application scope |

The four intents form a discriminated union. Extra fields and unknown intent values are rejected.

An anomaly request selects `all`, `long_resolution`, `overdue_high_priority`, or
`resolution_before_response`, with an optional time filter and bounded pagination. Step 10
executes these requests using deterministic rules documented in
`docs/ANOMALY_DETECTION.md`.

## Analytics operations

| Operation | Required fields | Result shape |
|---|---|---|
| List | Selected output fields | Matching ticket rows |
| Count | Filters and optional time filter | One integer |
| Aggregate | Numeric metric and average, minimum, maximum or sum | One numeric result |
| Grouped aggregate | Group field and aggregation; numeric metric except for grouped count | One row per group |

Grouping is restricted to agent, category, priority or status. Numeric metrics are restricted to response time, resolution time and customer rating.

## Filters

All filters in one request are combined with logical AND. Supported filter forms are:

- exact equality;
- membership such as High or Critical;
- greater than, greater than or equal, less than, and less than or equal for numeric fields;
- null and non-null checks for resolution time and customer rating;
- literal case-insensitive substring search over `issue_summary`.

`resolution_elapsed_hrs` is a derived numeric field used for “not resolved within”
questions. For a resolved ticket it is the recorded resolution duration. For an Open
or Escalated ticket it is the age from creation to the selected reference time.
Tickets created after the reference time have no elapsed value.

Each filter validates its field, operator and value together. Category, priority and status values must match documented values exactly. Numeric values must be finite and nonnegative. Customer-rating values must be integers from 1 through 5. Empty membership sets, duplicate values and blank strings are rejected.

## Time filters

A time filter selects either creation time or inferred resolution time. It contains exactly one of:

- this week, last week, this month or last month; or
- an explicit inclusive start and end date.

The shared Step 7 date module converts this representation into a half-open range using the visible reference clock.

## Selection sorting and limits

- List requests explicitly declare returned fields.
- Grouped results can sort only by their group or calculated result.
- Ticket lists cannot sort by an aggregate result.
- Duplicate selected or sort fields are rejected.
- Result limits range from 1 through 100 and default to 50.
- List and grouped operations accept an offset from 0 through 1,000,000. Counts and
  scalar aggregates are not paginated.
- List results include the full matching count before pagination. Grouped rankings
  include all groups tied at a result-ranked limit boundary.

## Representative requests

Critical unresolved ticket count:

```json
{
  "intent": "analytics",
  "operation": "count",
  "filters": [
    {"field": "priority", "operator": "eq", "value": "Critical"},
    {
      "field": "status",
      "operator": "in",
      "values": ["Open", "Escalated"]
    }
  ]
}
```

Agent with the most inferred resolutions this month:

```json
{
  "intent": "analytics",
  "operation": "grouped_aggregate",
  "filters": [
    {"field": "status", "operator": "eq", "value": "Resolved"}
  ],
  "aggregation": "count",
  "group_by": "agent_id",
  "time_filter": {
    "field": "resolved_at",
    "relative_period": "this_month"
  },
  "sort": [{"field": "result", "direction": "desc"}],
  "limit": 12
}
```

## Verification

Tests cover all four intents, every operation, every filter shape, relative and explicit dates, valid aggregations, grouping, sorting, field allowlists, limit boundaries, extra-field rejection and invalid semantic combinations. The generated JSON schema contains four top-level variants and does not expose raw SQL or Python execution fields.

Step 9 translates only these validated requests into parameterized, read-only SQLite
operations. Identifiers and SQL expressions come from fixed application allowlists;
filter text and numeric values are always bound parameters.
