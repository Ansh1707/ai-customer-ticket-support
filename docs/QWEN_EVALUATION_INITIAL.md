# Qwen2.5 3B Evaluation Report

Generated: 2026-09-17T16:50:20+00:00

Model: `qwen2.5:3b`
Dataset SHA-256: `812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff`
Dataset reference: `2024-04-05T00:00:00`

## Measured results

| Metric | Result |
|---|---:|
| Evaluation cases | 32 |
| Clearly supported cases | 27 |
| Held-out cases | 23 |
| Overall pass rate | 78.1% |
| Interpretation accuracy | 84.4% |
| Supported interpretation accuracy | 88.9% |
| Supported answer accuracy | 81.5% |
| Assessment sample pass rate | 100.0% |
| Held-out pass rate | 69.6% |
| Clarification accuracy | 50.0% |
| Invalid/prompt-injection safe handling | 66.7% |
| Execution failure rate | 0.0% |

## Latency

| Measurement | Mean | Median | P95 | Maximum |
|---|---:|---:|---:|---:|
| End-to-end | 5748.6 | 4602.6 | 12903.5 | 14494.4 |
| Interpretation | 5728.0 | 4592.1 | 12849.9 | 14481.5 |

## Case results

| ID | Category | Held out | Interpretation | Answer/safe outcome | Pass | Latency ms |
|---|---|---:|---:|---:|---:|---:|
| sample_open_count | assessment_sample | no | pass | pass | pass | 14494.4 |
| sample_agent_this_month | assessment_sample | no | pass | pass | pass | 6557.7 |
| sample_critical_over_12 | assessment_sample | no | pass | pass | pass | 8547.8 |
| sample_technical_rating | assessment_sample | no | pass | pass | pass | 3626.8 |
| sample_weekly_anomaly | assessment_sample | no | pass | pass | pass | 11903.1 |
| paraphrase_unresolved | unseen_paraphrase | yes | pass | pass | pass | 2828.0 |
| combined_critical_unresolved | combined_filters | yes | pass | pass | pass | 5915.5 |
| combined_priority_membership | combined_filters | yes | pass | pass | pass | 2518.1 |
| combined_open_technical | combined_filters | yes | pass | fail | fail | 7060.3 |
| combined_escalated_billing | combined_filters | yes | pass | fail | fail | 3899.5 |
| aggregate_billing_resolution | rankings_and_ratings | yes | pass | pass | pass | 4870.7 |
| ranking_lowest_agent_rating | rankings_and_ratings | yes | pass | pass | pass | 5880.5 |
| ranking_category_response | rankings_and_ratings | yes | pass | pass | pass | 4573.2 |
| explicit_march_resolution_ranking | explicit_dates | yes | fail | fail | fail | 8427.4 |
| relative_created_last_month | relative_dates | yes | pass | pass | pass | 4207.1 |
| relative_created_this_week | relative_dates | yes | pass | pass | pass | 3678.5 |
| relative_resolved_this_month | relative_dates | yes | pass | pass | pass | 4511.4 |
| aggregate_sum_critical_response | aggregates | yes | pass | pass | pass | 5501.2 |
| aggregate_min_technical_resolution | aggregates | yes | pass | pass | pass | 4346.6 |
| summary_dashboard_count | literal_summary_search | yes | pass | pass | pass | 4032.3 |
| summary_payment_list | literal_summary_search | yes | pass | pass | pass | 3737.6 |
| group_count_category | grouping | yes | fail | fail | fail | 7798.4 |
| aggregate_max_resolution | aggregates | yes | pass | pass | pass | 3552.3 |
| anomaly_all_rules | anomalies | yes | pass | pass | pass | 2739.7 |
| anomaly_overdue | anomalies | yes | fail | fail | fail | 9193.8 |
| anomaly_source_timing | anomalies | no | pass | pass | pass | 2882.1 |
| explicit_created_range | explicit_dates | yes | pass | pass | pass | 5994.8 |
| ambiguous_best_agent | ambiguous | no | pass | pass | pass | 4631.9 |
| ambiguous_context_reference | ambiguous | yes | fail | fail | fail | 3442.8 |
| unsupported_delete | unsupported | no | pass | pass | pass | 4952.0 |
| unsupported_prediction | unsupported | yes | fail | fail | fail | 14126.2 |
| prompt_injection | prompt_injection | no | pass | pass | pass | 3522.3 |

## Failures

### `combined_open_technical`

Question: List open Technical tickets.

Expected interpretation: `{"filters": [{"field": "status", "operator": "eq", "value": "Open"}, {"field": "category", "operator": "eq", "value": "Technical"}], "intent": "analytics", "operation": "list"}`

Actual interpretation: `{"aggregation": null, "filters": [{"field": "category", "operator": "eq", "value": "Technical"}, {"field": "priority", "operator": "in", "values": ["High", "Medium", "Low"]}, {"field": "status", "operator": "eq", "value": "Open"}], "group_by": null, "intent": "analytics", "limit": 50, "metric": null, "offset": 0, "operation": "list", "selected_fields": ["ticket_id", "created_at", "category", "priority", "status", "response_time_hrs", "resolution_time_hrs", "resolved_at", "agent_id", "customer_rating", "issue_summary", "unresolved_age_hrs", "resolution_elapsed_hrs"], "sort": [{"direction": "asc", "field": "created_at"}], "time_filter": null}`

Expected answer evidence: `{"data": {"matching_count": 30}, "matching_count": 30, "outcome": "ok"}`

Actual answer: Found and returned 28 matching tickets.

### `combined_escalated_billing`

Question: How many Billing tickets are Escalated?

Expected interpretation: `{"filters": [{"field": "category", "operator": "eq", "value": "Billing"}, {"field": "status", "operator": "eq", "value": "Escalated"}], "intent": "analytics", "operation": "count"}`

Actual interpretation: `{"aggregation": null, "filters": [{"field": "category", "operator": "eq", "value": "Billing"}, {"field": "status", "operator": "eq", "value": "Escalated"}, {"case_sensitive": false, "field": "issue_summary", "operator": "contains", "value": "Billing"}], "group_by": null, "intent": "analytics", "limit": 50, "metric": null, "offset": 0, "operation": "count", "selected_fields": [], "sort": [], "time_filter": null}`

Expected answer evidence: `{"data": {"value": 16}, "matching_count": 16, "outcome": "ok"}`

Actual answer: 0 tickets match the interpreted request.

### `explicit_march_resolution_ranking`

Question: Which agent resolved the most tickets from March 1 through March 31, 2024?

Expected interpretation: `{"aggregation": "count", "group_by": "agent_id", "intent": "analytics", "operation": "grouped_aggregate", "sort": [{"direction": "desc", "field": "result"}], "time_filter": {"end_date": "2024-03-31", "field": "resolved_at", "start_date": "2024-03-01"}}`

Actual interpretation: `{"aggregation": "count", "filters": [{"field": "status", "operator": "eq", "value": "Resolved"}], "group_by": "agent_id", "intent": "analytics", "limit": 50, "metric": null, "offset": 0, "operation": "grouped_aggregate", "selected_fields": [], "sort": [{"direction": "desc", "field": "result"}], "time_filter": {"end_date": null, "field": "resolved_at", "relative_period": "this_month", "start_date": null}}`

Expected answer evidence: `{"data": {"rows": [{"group_value": "AGT-01", "value": 16}]}, "outcome": "ok"}`

Actual answer: The highest ticket count by agent id is 1 for AGT-07. Applied range: 2024-04-01 00:00 to 2024-04-05 00:00 (end excluded; this month).

### `group_count_category`

Question: Show the ticket count for each category.

Expected interpretation: `{"aggregation": "count", "group_by": "category", "intent": "analytics", "operation": "grouped_aggregate"}`

Actual interpretation: `{"aggregation": null, "filters": [], "group_by": null, "intent": "analytics", "limit": 50, "metric": null, "offset": 0, "operation": "list", "selected_fields": ["ticket_id", "created_at", "category", "priority", "status", "response_time_hrs", "resolution_time_hrs", "resolved_at", "agent_id", "customer_rating", "issue_summary", "unresolved_age_hrs", "resolution_elapsed_hrs"], "sort": [{"direction": "asc", "field": "category"}], "time_filter": null}`

Expected answer evidence: `{"data": {"matching_group_count": 3, "rows": [{"group_value": "Billing", "value": 159}, {"group_value": "General", "value": 189}, {"group_value": "Technical", "value": 152}]}, "outcome": "ok"}`

Actual answer: Found 500 matching tickets and returned 50 from offset 0.

### `anomaly_overdue`

Question: Find overdue unresolved High or Critical tickets older than 24 hours.

Expected interpretation: `{"intent": "anomalies", "rule": "overdue_high_priority"}`

Actual interpretation: `{"aggregation": null, "filters": [{"field": "priority", "operator": "in", "values": ["High", "Critical"]}, {"field": "status", "operator": "in", "values": ["Open", "Escalated"]}, {"field": "resolution_elapsed_hrs", "operator": "gt", "value": 24.0}], "group_by": null, "intent": "analytics", "limit": 50, "metric": null, "offset": 0, "operation": "list", "selected_fields": ["ticket_id", "created_at", "category", "priority", "status", "response_time_hrs", "resolution_time_hrs", "resolved_at", "agent_id", "customer_rating", "issue_summary", "unresolved_age_hrs", "resolution_elapsed_hrs"], "sort": [{"direction": "asc", "field": "resolution_elapsed_hrs"}], "time_filter": null}`

Expected answer evidence: `{"data": {"matching_ticket_count": 80, "rule_counts": {"overdue_high_priority": 80}}, "matching_count": 80, "outcome": "ok"}`

Actual answer: Found 80 matching tickets and returned 50 from offset 0. Reference time: 2024-04-05 00:00 dataset-local.

### `ambiguous_context_reference`

Question: What about those tickets?

Expected interpretation: `{"intent": "clarification"}`

Actual interpretation: `{"aggregation": null, "filters": [{"field": "priority", "operator": "eq", "value": "High"}], "group_by": null, "intent": "analytics", "limit": 50, "metric": null, "offset": 0, "operation": "list", "selected_fields": ["ticket_id", "created_at", "category", "priority", "status", "response_time_hrs", "resolution_time_hrs", "resolved_at", "agent_id", "customer_rating", "issue_summary", "unresolved_age_hrs", "resolution_elapsed_hrs"], "sort": [], "time_filter": null}`

Expected answer evidence: `{"outcome": "clarification"}`

Actual answer: Found 134 matching tickets and returned 50 from offset 0.

### `unsupported_prediction`

Question: Predict how many tickets will arrive next month.

Expected interpretation: `{"intent": "unsupported"}`

Actual interpretation: `{"aggregation": null, "filters": [], "group_by": null, "intent": "analytics", "limit": 50, "metric": null, "offset": 0, "operation": "count", "selected_fields": [], "sort": [], "time_filter": null}`

Expected answer evidence: `{"outcome": "unsupported"}`

Actual answer: 500 tickets match the interpreted request.

## Target assessment

The Step 25 target was not fully met; failures are reported above.

The benchmark contains expected interpretations and independently checked answer evidence. Prompt-exposed cases are labeled; all other cases remain held out from exact prompt examples. Metrics reflect this recorded run and are not a guarantee of future model behavior.
