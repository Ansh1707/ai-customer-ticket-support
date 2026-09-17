# Date and Reference Clock Handling

Step 7 defines the date policy once for analytics, anomaly detection, the API and the UI. The source timestamps do not specify a timezone, so the application treats them as dataset-local wall-clock values and does not silently convert them.

## Reference modes

| Mode | Behavior |
|---|---|
| Dataset | Midnight at the beginning of the day after the latest ticket creation or inferred resolution event |
| Current | The computer's current local wall-clock time |
| Custom | A user-supplied dataset-local timestamp without timezone metadata |

The supplied dataset's latest event is ticket `TKT-108` with an inferred resolution at April 4, 2024 at 12:23. Its default reference is therefore April 5, 2024 at 00:00.

If a selected reference precedes recorded events, the date layer emits `reference_precedes_dataset_events`. Age calculations exclude tickets created after that reference. The warning also explains that the snapshot cannot reconstruct past ticket statuses.

## Relative calendar periods

Weeks begin on Monday. Ranges include their start and exclude their end.

For the default April 5 reference:

| Phrase | Start included | End excluded |
|---|---|---|
| This week | April 1, 2024 at 00:00 | April 5, 2024 at 00:00 |
| Last week | March 25, 2024 at 00:00 | April 1, 2024 at 00:00 |
| This month | April 1, 2024 at 00:00 | April 5, 2024 at 00:00 |
| Last month | March 1, 2024 at 00:00 | April 1, 2024 at 00:00 |

An in-progress period ends at the selected reference, not at a future week or month boundary. At the exact beginning of a week or month, the corresponding current-period range is valid but empty.

## Explicit ranges

- A date-only range treats both user-facing dates as inclusive. Internally, its end becomes midnight after the final date.
- A timestamp range is half-open: its start is included and its end is excluded.
- Reversed ranges and timezone-bearing timestamps are rejected.

This makes adjacent ranges non-overlapping and prevents records on a boundary from being counted twice.

## Ticket timestamps

- Creation-based questions use `created_at`.
- Resolution-based questions use the inferred timestamp `created_at + resolution_time_hrs` for resolved tickets.
- Unresolved tickets do not have an inferred resolution timestamp.
- A general phrase such as “tickets this month” defaults to creation time. A phrase such as “resolved this month” uses inferred resolution time.

For this dataset, zero tickets were created in the default April current-month range, while one ticket has an inferred resolution in the default current-week range.

## Unresolved age

Unresolved age is `(reference - created_at)` in hours for Open or Escalated tickets created at or before the reference.

- Resolved tickets return no unresolved age.
- Tickets created after the reference return no age and are excluded from overdue evaluation.
- A ticket created exactly at the reference has age zero.
- Threshold rules will use strict greater-than comparisons in the anomaly step.

## Historical status limitation

The file contains a single status snapshot. It can answer questions using the supplied current status and can filter creation or inferred resolution events by date. It cannot determine what a ticket's status was on an earlier date because no status-change history is provided.

The API and UI must display this limitation when a question asks for historical status. That response will be wired in during the interpretation and presentation steps.
