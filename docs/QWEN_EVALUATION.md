# Qwen2.5 3B Evaluation Report

Generated: 2026-09-18T07:28:59+00:00

Model: `qwen2.5:3b`
Dataset SHA-256: `812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff`
Dataset reference: `2024-04-05T00:00:00`

## Measured results

| Metric | Result |
|---|---:|
| Evaluation cases | 39 |
| Clearly supported cases | 34 |
| Held-out cases | 30 |
| Overall pass rate | 100.0% |
| Interpretation accuracy | 100.0% |
| Supported interpretation accuracy | 100.0% |
| Supported answer accuracy | 100.0% |
| Assessment sample pass rate | 100.0% |
| Held-out pass rate | 100.0% |
| Clarification accuracy | 100.0% |
| Invalid/prompt-injection safe handling | 100.0% |
| Execution failure rate | 0.0% |

## Latency

| Measurement | Mean | Median | P95 | Maximum |
|---|---:|---:|---:|---:|
| End-to-end | 5824.2 | 4422.0 | 13232.2 | 16816.8 |
| Interpretation | 5800.5 | 4407.3 | 13196.3 | 16805.4 |

## Case results

| ID | Category | Held out | Interpretation | Answer/safe outcome | Pass | Latency ms |
|---|---|---:|---:|---:|---:|---:|
| sample_open_count | assessment_sample | no | pass | pass | pass | 16816.8 |
| sample_agent_this_month | assessment_sample | no | pass | pass | pass | 9988.7 |
| sample_critical_over_12 | assessment_sample | no | pass | pass | pass | 8515.0 |
| sample_technical_rating | assessment_sample | no | pass | pass | pass | 3858.4 |
| sample_weekly_anomaly | assessment_sample | no | pass | pass | pass | 12842.3 |
| paraphrase_unresolved | unseen_paraphrase | yes | pass | pass | pass | 2223.9 |
| combined_critical_unresolved | combined_filters | yes | pass | pass | pass | 6063.9 |
| combined_priority_membership | combined_filters | yes | pass | pass | pass | 2393.9 |
| combined_open_technical | combined_filters | yes | pass | pass | pass | 5229.1 |
| combined_escalated_billing | combined_filters | yes | pass | pass | pass | 8499.4 |
| aggregate_billing_resolution | rankings_and_ratings | yes | pass | pass | pass | 4400.3 |
| ranking_lowest_agent_rating | rankings_and_ratings | yes | pass | pass | pass | 5740.3 |
| ranking_category_response | rankings_and_ratings | yes | pass | pass | pass | 4762.3 |
| explicit_march_resolution_ranking | explicit_dates | yes | pass | pass | pass | 16741.4 |
| relative_created_last_month | relative_dates | yes | pass | pass | pass | 7855.2 |
| relative_created_this_week | relative_dates | yes | pass | pass | pass | 5269.0 |
| relative_resolved_this_month | relative_dates | yes | pass | pass | pass | 5213.3 |
| aggregate_sum_critical_response | aggregates | yes | pass | pass | pass | 9605.7 |
| aggregate_min_technical_resolution | aggregates | yes | pass | pass | pass | 8270.9 |
| summary_dashboard_count | literal_summary_search | yes | pass | pass | pass | 3260.6 |
| summary_payment_list | literal_summary_search | yes | pass | pass | pass | 2857.5 |
| group_count_category | grouping | yes | pass | pass | pass | 4355.6 |
| aggregate_max_resolution | aggregates | yes | pass | pass | pass | 3367.1 |
| anomaly_all_rules | anomalies | yes | pass | pass | pass | 2624.7 |
| anomaly_overdue | anomalies | yes | pass | pass | pass | 3532.0 |
| anomaly_source_timing | anomalies | no | pass | pass | pass | 2586.6 |
| explicit_created_range | explicit_dates | yes | pass | pass | pass | 5646.7 |
| ambiguous_best_agent | ambiguous | no | pass | pass | pass | 4329.2 |
| ambiguous_context_reference | ambiguous | yes | pass | pass | pass | 6398.6 |
| unsupported_delete | unsupported | no | pass | pass | pass | 4077.1 |
| unsupported_prediction | unsupported | yes | pass | pass | pass | 3429.8 |
| prompt_injection | prompt_injection | no | pass | pass | pass | 1933.5 |
| regression_negated_priority | negation | yes | pass | pass | pass | 2814.2 |
| regression_unresolved_synonym | unseen_paraphrase | yes | pass | pass | pass | 2087.8 |
| regression_created_date_precedence | relative_dates | yes | pass | pass | pass | 4422.0 |
| regression_explicit_anomaly_range | explicit_dates | yes | pass | pass | pass | 3639.3 |
| regression_multiple_numeric_filters | combined_filters | yes | pass | pass | pass | 7214.1 |
| regression_top_three_agents | rankings_and_ratings | yes | pass | pass | pass | 10483.8 |
| regression_exact_rating | combined_filters | yes | pass | pass | pass | 3793.4 |

## Failures

No evaluation cases failed.

## Target assessment

The Step 25 target was met.

The benchmark contains expected interpretations and independently checked answer evidence. Prompt-exposed cases are labeled; all other cases remain held out from exact prompt examples. Metrics reflect this recorded run and are not a guarantee of future model behavior.
