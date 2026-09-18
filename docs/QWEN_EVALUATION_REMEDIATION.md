# Qwen2.5 3B Evaluation Report

Generated: 2026-09-18T12:06:20+00:00

Model: `qwen2.5:3b`
Dataset SHA-256: `812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff`
Dataset reference: `2024-04-05T00:00:00`

## Measured results

| Metric | Result |
|---|---:|
| Evaluation cases | 51 |
| Clearly supported cases | 45 |
| Cases outside exact prompt examples | 42 |
| Overall pass rate | 100.0% |
| Interpretation accuracy | 100.0% |
| Supported interpretation accuracy | 100.0% |
| Supported answer accuracy | 100.0% |
| Assessment sample pass rate | 100.0% |
| Non-prompt-example regression pass rate | 100.0% |
| Clarification accuracy | 100.0% |
| Invalid/prompt-injection safe handling | 100.0% |
| Execution failure rate | 0.0% |

## Latency

| Measurement | Mean | Median | P95 | Maximum |
|---|---:|---:|---:|---:|
| End-to-end | 5375.4 | 3887.7 | 8511.8 | 56769.9 |
| Interpretation | 5361.2 | 3870.7 | 8500.6 | 56750.3 |

## Case results

| ID | Category | Prompt example | Interpretation | Answer/safe outcome | Pass | Latency ms |
|---|---|---:|---:|---:|---:|---:|
| sample_open_count | assessment_sample | yes | pass | pass | pass | 2658.4 |
| sample_agent_this_month | assessment_sample | yes | pass | pass | pass | 5907.1 |
| sample_critical_over_12 | assessment_sample | yes | pass | pass | pass | 5375.0 |
| sample_technical_rating | assessment_sample | yes | pass | pass | pass | 3476.3 |
| sample_weekly_anomaly | assessment_sample | yes | pass | pass | pass | 3896.0 |
| paraphrase_unresolved | unseen_paraphrase | no | pass | pass | pass | 2563.6 |
| combined_critical_unresolved | combined_filters | no | pass | pass | pass | 3580.6 |
| combined_priority_membership | combined_filters | no | pass | pass | pass | 3133.3 |
| combined_open_technical | combined_filters | no | pass | pass | pass | 5540.1 |
| combined_escalated_billing | combined_filters | no | pass | pass | pass | 3507.0 |
| aggregate_billing_resolution | rankings_and_ratings | no | pass | pass | pass | 3415.6 |
| ranking_lowest_agent_rating | rankings_and_ratings | no | pass | pass | pass | 7371.2 |
| ranking_category_response | rankings_and_ratings | no | pass | pass | pass | 4626.7 |
| explicit_march_resolution_ranking | explicit_dates | no | pass | pass | pass | 7746.3 |
| relative_created_last_month | relative_dates | no | pass | pass | pass | 6846.8 |
| relative_created_this_week | relative_dates | no | pass | pass | pass | 3887.7 |
| relative_resolved_this_month | relative_dates | no | pass | pass | pass | 3629.1 |
| aggregate_sum_critical_response | aggregates | no | pass | pass | pass | 3290.2 |
| aggregate_min_technical_resolution | aggregates | no | pass | pass | pass | 3504.5 |
| summary_dashboard_count | literal_summary_search | no | pass | pass | pass | 2407.7 |
| summary_payment_list | literal_summary_search | no | pass | pass | pass | 2333.0 |
| group_count_category | grouping | no | pass | pass | pass | 5931.6 |
| aggregate_max_resolution | aggregates | no | pass | pass | pass | 4604.3 |
| anomaly_all_rules | anomalies | no | pass | pass | pass | 2581.1 |
| anomaly_overdue | anomalies | no | pass | pass | pass | 4211.9 |
| anomaly_source_timing | anomalies | yes | pass | pass | pass | 2874.0 |
| explicit_created_range | explicit_dates | no | pass | pass | pass | 4867.3 |
| ambiguous_best_agent | ambiguous | yes | pass | pass | pass | 4340.9 |
| ambiguous_context_reference | ambiguous | no | pass | pass | pass | 6650.7 |
| unsupported_delete | unsupported | yes | pass | pass | pass | 3891.7 |
| unsupported_prediction | unsupported | no | pass | pass | pass | 3798.1 |
| prompt_injection | prompt_injection | yes | pass | pass | pass | 2146.1 |
| regression_negated_priority | negation | no | pass | pass | pass | 2456.5 |
| regression_unresolved_synonym | unseen_paraphrase | no | pass | pass | pass | 2271.1 |
| regression_created_date_precedence | relative_dates | no | pass | pass | pass | 5068.0 |
| regression_explicit_anomaly_range | explicit_dates | no | pass | pass | pass | 4094.3 |
| regression_multiple_numeric_filters | combined_filters | no | pass | pass | pass | 9277.3 |
| regression_top_three_agents | rankings_and_ratings | no | pass | pass | pass | 6113.4 |
| regression_exact_rating | combined_filters | no | pass | pass | pass | 3610.3 |
| contrast_quoted_resolved_summary | contrast_quoted_literals | no | pass | pass | pass | 2616.1 |
| contrast_resolved_status | contrast_quoted_literals | no | pass | pass | pass | 2294.2 |
| contrast_quoted_critical_summary | contrast_quoted_literals | no | pass | pass | pass | 2727.2 |
| contrast_critical_priority | contrast_polarity | no | pass | pass | pass | 2370.4 |
| contrast_excluding_critical | contrast_polarity | no | pass | pass | pass | 56769.9 |
| contrast_created_march | contrast_date_field | no | pass | pass | pass | 5720.1 |
| contrast_resolved_march | contrast_date_field | no | pass | pass | pass | 9486.8 |
| contrast_single_numeric_condition | contrast_numeric_arity | no | pass | pass | pass | 4893.8 |
| contrast_two_numeric_conditions | contrast_numeric_arity | no | pass | pass | pass | 7631.7 |
| contrast_exact_rating | contrast_numeric_operator | no | pass | pass | pass | 3639.9 |
| contrast_greater_rating | contrast_numeric_operator | no | pass | pass | pass | 3430.1 |
| prompt_injection_mutation_variant | prompt_injection | no | pass | pass | pass | 5082.5 |

## Failures

No evaluation cases failed.

## Target assessment

The Step 25 target was met.

The benchmark contains expected interpretations and independently checked answer evidence. Cases outside exact prompt examples are development and regression cases: prior failures may have influenced their prompts or safeguards. They are not an untouched final test set. Metrics reflect this recorded run and are not evidence of independent generalization or a guarantee of future model behavior.
