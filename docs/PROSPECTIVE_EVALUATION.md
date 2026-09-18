> Prospective first run: 8/9 against the original labels. A subsequent independent
> CSV check established that the sole failed label was wrong: literal `ratio`
> matches 18 summaries containing `Integration`, not zero. The application returned
> 18 correctly. Adjudicated result: 9/9. Original labels/results remain unchanged;
> see `evaluation/prospective_label_adjudication.json`. No implementation tuning
> or repeat inference followed this discovery. This set is not independently authored.

# Qwen2.5 3B Evaluation Report

Generated: 2026-09-18T12:00:19+00:00

Model: `qwen2.5:3b`
Dataset SHA-256: `812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff`
Dataset reference: `2024-04-05T00:00:00`

## Measured results

| Metric | Result |
|---|---:|
| Evaluation cases | 9 |
| Clearly supported cases | 5 |
| Cases outside exact prompt examples | 9 |
| Overall pass rate | 88.9% |
| Interpretation accuracy | 100.0% |
| Supported interpretation accuracy | 100.0% |
| Supported answer accuracy | 80.0% |
| Assessment sample pass rate | N/A (no cases) |
| Non-prompt-example regression pass rate | 88.9% |
| Clarification accuracy | N/A (no cases) |
| Invalid/prompt-injection safe handling | N/A (no cases) |
| Execution failure rate | 0.0% |

## Latency

| Measurement | Mean | Median | P95 | Maximum |
|---|---:|---:|---:|---:|
| End-to-end | 7017.1 | 7141.9 | 15023.9 | 16183.8 |
| Interpretation | 6986.3 | 7033.3 | 14998.6 | 16159.7 |

## Case results

| ID | Category | Prompt example | Interpretation | Answer/safe outcome | Pass | Latency ms |
|---|---|---:|---:|---:|---:|---:|
| null_paraphrase | prospective | no | pass | pass | pass | 10517.9 |
| nonnull_paraphrase | prospective | no | pass | pass | pass | 16183.8 |
| negated_status | prospective | no | pass | pass | pass | 13284.1 |
| quoted_operator | prospective | no | pass | fail | fail | 7237.5 |
| percentile | prospective | no | pass | pass | pass | 2190.6 |
| proportion | prospective | no | pass | pass | pass | 2192.6 |
| logical_cross_field | prospective | no | pass | pass | pass | 1052.7 |
| dual_event | prospective | no | pass | pass | pass | 3352.9 |
| first_two | prospective | no | pass | pass | pass | 7141.9 |

## Failures

### `quoted_operator`

Question: How many issue summaries contain "ratio"?

Expected interpretation: `{"intent": "analytics"}`

Actual interpretation: `{"aggregation": null, "filters": [{"case_sensitive": false, "field": "issue_summary", "operator": "contains", "value": "ratio"}], "group_by": null, "intent": "analytics", "limit": 50, "metric": null, "offset": 0, "operation": "count", "result_limit": null, "selected_fields": [], "sort": [], "time_filter": null}`

Expected answer evidence: `{"data": {"value": 0}, "outcome": "ok"}`

Actual answer: 18 tickets match the interpreted request.


## Target assessment

The Step 25 target is not assessed by this case set.

The benchmark contains expected interpretations and independently checked answer evidence. Cases outside exact prompt examples are development and regression cases: prior failures may have influenced their prompts or safeguards. They are not an untouched final test set. Metrics reflect this recorded run and are not evidence of independent generalization or a guarantee of future model behavior.
