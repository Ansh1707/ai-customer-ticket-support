# Qwen2.5 3B Evaluation Report

Generated: 2026-09-18T11:55:46+00:00

Model: `qwen2.5:3b`
Dataset SHA-256: `812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff`
Dataset reference: `2024-04-05T00:00:00`

## Measured results

| Metric | Result |
|---|---:|
| Evaluation cases | 16 |
| Clearly supported cases | 9 |
| Cases outside exact prompt examples | 16 |
| Overall pass rate | 100.0% |
| Interpretation accuracy | 100.0% |
| Supported interpretation accuracy | 100.0% |
| Supported answer accuracy | 100.0% |
| Assessment sample pass rate | N/A (no cases) |
| Non-prompt-example regression pass rate | 100.0% |
| Clarification accuracy | N/A (no cases) |
| Invalid/prompt-injection safe handling | N/A (no cases) |
| Execution failure rate | 0.0% |

## Latency

| Measurement | Mean | Median | P95 | Maximum |
|---|---:|---:|---:|---:|
| End-to-end | 4434.6 | 3406.8 | 11831.9 | 14872.4 |
| Interpretation | 4405.2 | 3373.0 | 11774.6 | 14656.1 |

## Case results

| ID | Category | Prompt example | Interpretation | Answer/safe outcome | Pass | Latency ms |
|---|---|---:|---:|---:|---:|---:|
| percentage | capability_boundary | no | pass | pass | pass | 10818.3 |
| median | capability_boundary | no | pass | pass | pass | 1090.9 |
| cross_field_or | capability_boundary | no | pass | pass | pass | 1124.7 |
| dual_dates | capability_boundary | no | pass | pass | pass | 1148.0 |
| ratio | capability_boundary | no | pass | pass | pass | 1460.4 |
| numeric_or | capability_boundary | no | pass | pass | pass | 1432.8 |
| oversized_limit | capability_boundary | no | pass | pass | pass | 1850.1 |
| missing_rating | capability_boundary | no | pass | pass | pass | 14872.4 |
| present_rating | capability_boundary | no | pass | pass | pass | 4751.8 |
| missing_resolution | capability_boundary | no | pass | pass | pass | 7820.9 |
| not_open | capability_boundary | no | pass | pass | pass | 3209.2 |
| rating_gte | capability_boundary | no | pass | pass | pass | 3604.3 |
| priority_or | capability_boundary | no | pass | pass | pass | 2838.4 |
| quoted_statistics | capability_boundary | no | pass | pass | pass | 4157.8 |
| five_agents | capability_boundary | no | pass | pass | pass | 5876.6 |
| three_oldest | capability_boundary | no | pass | pass | pass | 4897.5 |

## Failures

No evaluation cases failed.

## Target assessment

The Step 25 target is not assessed by this case set.

The benchmark contains expected interpretations and independently checked answer evidence. Cases outside exact prompt examples are development and regression cases: prior failures may have influenced their prompts or safeguards. They are not an untouched final test set. Metrics reflect this recorded run and are not evidence of independent generalization or a guarantee of future model behavior.
