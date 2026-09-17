# Qwen2.5 3B Evaluation Report

Generated: 2026-09-17T21:49:49+00:00

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
| End-to-end | 4394.6 | 3894.6 | 7666.4 | 9673.9 |
| Interpretation | 4376.1 | 3876.6 | 7649.2 | 9649.5 |

## Case results

| ID | Category | Held out | Interpretation | Answer/safe outcome | Pass | Latency ms |
|---|---|---:|---:|---:|---:|---:|
| sample_open_count | assessment_sample | no | pass | pass | pass | 3888.2 |
| sample_agent_this_month | assessment_sample | no | pass | pass | pass | 6059.6 |
| sample_critical_over_12 | assessment_sample | no | pass | pass | pass | 5185.4 |
| sample_technical_rating | assessment_sample | no | pass | pass | pass | 3141.6 |
| sample_weekly_anomaly | assessment_sample | no | pass | pass | pass | 9673.9 |
| paraphrase_unresolved | unseen_paraphrase | yes | pass | pass | pass | 2024.2 |
| combined_critical_unresolved | combined_filters | yes | pass | pass | pass | 6583.1 |
| combined_priority_membership | combined_filters | yes | pass | pass | pass | 3833.7 |
| combined_open_technical | combined_filters | yes | pass | pass | pass | 7480.1 |
| combined_escalated_billing | combined_filters | yes | pass | pass | pass | 4363.3 |
| aggregate_billing_resolution | rankings_and_ratings | yes | pass | pass | pass | 4329.1 |
| ranking_lowest_agent_rating | rankings_and_ratings | yes | pass | pass | pass | 5453.4 |
| ranking_category_response | rankings_and_ratings | yes | pass | pass | pass | 4169.6 |
| explicit_march_resolution_ranking | explicit_dates | yes | pass | pass | pass | 9343.1 |
| relative_created_last_month | relative_dates | yes | pass | pass | pass | 3894.6 |
| relative_created_this_week | relative_dates | yes | pass | pass | pass | 4176.3 |
| relative_resolved_this_month | relative_dates | yes | pass | pass | pass | 3122.0 |
| aggregate_sum_critical_response | aggregates | yes | pass | pass | pass | 3292.2 |
| aggregate_min_technical_resolution | aggregates | yes | pass | pass | pass | 3043.5 |
| summary_dashboard_count | literal_summary_search | yes | pass | pass | pass | 2201.6 |
| summary_payment_list | literal_summary_search | yes | pass | pass | pass | 2203.8 |
| group_count_category | grouping | yes | pass | pass | pass | 3098.4 |
| aggregate_max_resolution | aggregates | yes | pass | pass | pass | 6539.3 |
| anomaly_all_rules | anomalies | yes | pass | pass | pass | 2545.5 |
| anomaly_overdue | anomalies | yes | pass | pass | pass | 3889.5 |
| anomaly_source_timing | anomalies | no | pass | pass | pass | 2695.8 |
| explicit_created_range | explicit_dates | yes | pass | pass | pass | 6799.4 |
| ambiguous_best_agent | ambiguous | no | pass | pass | pass | 4347.8 |
| ambiguous_context_reference | ambiguous | yes | pass | pass | pass | 6248.5 |
| unsupported_delete | unsupported | no | pass | pass | pass | 3802.7 |
| unsupported_prediction | unsupported | yes | pass | pass | pass | 3553.9 |
| prompt_injection | prompt_injection | no | pass | pass | pass | 1922.4 |
| regression_negated_priority | negation | yes | pass | pass | pass | 3154.0 |
| regression_unresolved_synonym | unseen_paraphrase | yes | pass | pass | pass | 2220.0 |
| regression_created_date_precedence | relative_dates | yes | pass | pass | pass | 4890.3 |
| regression_explicit_anomaly_range | explicit_dates | yes | pass | pass | pass | 4611.5 |
| regression_multiple_numeric_filters | combined_filters | yes | pass | pass | pass | 5925.0 |
| regression_top_three_agents | rankings_and_ratings | yes | pass | pass | pass | 3574.2 |
| regression_exact_rating | combined_filters | yes | pass | pass | pass | 4107.6 |

## Failures

No evaluation cases failed.

## Target assessment

The Step 25 target was met.

The benchmark contains expected interpretations and independently checked answer evidence. Prompt-exposed cases are labeled; all other cases remain held out from exact prompt examples. Metrics reflect this recorded run and are not a guarantee of future model behavior.
