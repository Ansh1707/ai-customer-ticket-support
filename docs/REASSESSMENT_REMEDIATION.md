# Strict reassessment remediation — September 18, 2026

This change addresses the observed successful-but-wrong answers while preserving the
assessment's scope: CSV ingestion, LLM-backed natural-language analytics, explainable
anomalies, REST API and minimal UI. It does not claim universal language correctness
or guarantee an evaluator's score.

## Behavior changes

| Previously failing request | Current policy |
|---|---|
| No customer rating | Execute `is_null`; 173 tickets |
| Recorded customer rating | Execute `is_not_null`; 327 tickets |
| Which 5 agents have fastest average response time? | Five ranked rows: AGT-09, AGT-10, AGT-08, AGT-02, AGT-06 |
| Show the 3 oldest unresolved tickets | TKT-054, TKT-233, TKT-289, in that order |
| Percentage resolved / median resolution time | Clarification explaining unsupported statistic; no execution |
| Open or Technical | Clarification explaining unsupported cross-field OR; no execution |
| Resolved in March, created in February | Clarification explaining the one-date-range contract; no execution |

Support for median, ratios, arbitrary Boolean expressions and two date predicates was
not added. Explicit capability rejection is the selected solution to semantic
substitution, as permitted by the reassessment. Same-field categorical alternatives,
existing numeric comparisons, anomaly rules and assessment queries remain supported.
The language gate is deliberately bounded; unrecognized wording still needs review.

## Architecture and startup

- `llm.py`: HTTP transport, timeout, retries and interpretation orchestration.
- `llm_prompts.py`: router/extraction prompts.
- `llm_plans.py`: compact model-facing schemas, including typed null conditions.
- `llm_language.py`: literal cue extraction.
- `llm_semantics.py`: plan compilation, reconciliation and completeness checks.
- `capabilities.py`: explicit unsupported families and result/null cues.

The launcher runs bounded model warm-up before starting the interface. Requests set
ten-minute residency; `--skip-model-warmup` opts out. A warm-up failure is logged and
does not block deterministic functionality. This moves inference initialization into
startup, not out of the total system cost. No cold-start speedup percentage is claimed.

## Verification and evidence boundaries

The 16-case capability regression passed all cases against real `qwen2.5:3b`.
Seven unsupported cases require clarification, null data and exactly zero execution
time. Nine supported cases validate answers, including exact ranking cardinality and
order. See `evaluation/capability_regression_results.json` and
[CAPABILITY_REGRESSION.md](CAPABILITY_REGRESSION.md).

`evaluation/prospective_cases.json` was authored after implementation froze. The
source and cases are identified by SHA-256 in `evaluation/prospective_freeze.json`.
Its first run is recorded separately. No implementation or prompt tuning is permitted
on those results without reclassifying the set as regression evidence. The author
knows the prior development cases, so this is not an independent blind evaluation.
An independently authored evaluator set is still needed to estimate generalization.

For reproducibility, the regular 51-case evaluation is development/regression evidence.
The initial historical report remains historical. Counts from earlier clean installs
are not relabeled as current environment verification. UI state transitions and corrupt
database tests are deterministic coverage, not live-Qwen tests.

## Remaining manual evaluator work

No manual setup change is required for the code fixes. For independent assessment,
freeze this revision, have another person author questions and expected CSV-derived
answers without viewing the prompts, and run them once. Retain failures. Any subsequent
tuning turns that set into development evidence and requires a new independent set.

## Final measured checks

- Offline suite: 255 passed; 34 live tests intentionally skipped (5.72 seconds).
- Live Qwen suite: 34/34 passed (200.27 seconds).
- Capability regression: 16/16 passed.
- Prospective first run: 8/9 against frozen labels; independent raw-CSV adjudication
  establishes 9/9 correct application results. The original zero-match expectation
  for literal `ratio` was wrong: it matches 18 `Integration` summaries. The original
  case, report, matching IDs and correction are retained; source hashes remain intact.
- Ruff, compileall, dependency checks and repository audit passed.

These durations are measurements from individual runs, not hardware-normalized
performance benchmarks. Some late live checks overlapped the prospective run.
The prospective checks establish only those cases, not unrestricted-language accuracy.

The final 51-case regression passed **51/51**, generated at `2026-09-18T12:06:20+00:00`, with
5,375.4 ms mean end-to-end latency and 8,511.8 ms P95. Raw results are
`evaluation/qwen_eval_results.remediation.json`; the original evaluation remains
unchanged. All measured figures refer to identified individual runs.

The real launcher smoke check used isolated ports 18994/18995 and a temporary
snapshot. It warmed Qwen, reached `ready`, served Streamlit with HTTP 200, answered
missing ratings with 173 in 3,457.5 ms, and released both ports after Ctrl+C.
No new browser interaction was claimed; UI transitions are covered by the existing
Streamlit component tests. The model benchmark retained a 56,769.9 ms maximum
alongside its 5,375.4 ms mean and 8,511.8 ms P95. Warm-up is a mitigation, not a
promise that every request will be fast.
