# Setup Verification

This file records the evidence gathered for planning Steps 2 and 3. It is not a claim that the application itself has been implemented or accepted.

## Machine baseline

Verified on September 17, 2026.

| Item | Verified value |
|---|---|
| Computer | MacBook Air, model identifier MacBookAir10,1 |
| Processor | Apple M1, 8 cores |
| Memory | 8 GB |
| Architecture | Apple Silicon arm64 |
| macOS | 27.0, build 26A428 |
| Available workspace volume space | Approximately 113 GiB |
| Python | 3.11.12 |
| SQLite through Python | 3.53.4 |
| Git | 2.54.0, Apple Git-157 |
| Local Git author | Ansh, `ansharyan1707@gmail.com` |
| GitHub CLI | Authenticated as `Ansh1707` through the macOS keyring; HTTPS Git operations enabled |
| Ollama client | 0.34.1 |
| Virtual environment | `.venv`, Python 3.11.12 |
| Python dependency check | Passed; no broken requirements reported |

The assessment was received on September 16, 2026 at 18:30 IST. The 48-hour deadline is September 18, 2026 at 18:30 IST. A local Git repository was initialized on branch `main` after the baseline check.

## Dataset identity

| Item | Verified value |
|---|---|
| File | `support_tickets.csv` |
| SHA-256 | `812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff` |

The checksum is the preservation reference for later ingestion and clean-run checks.

## Qwen model verification

| Item | Verified value |
|---|---|
| Model | `qwen2.5:3b` |
| Digest | `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b` |
| Parameter size | 3.1B |
| Quantization | Q4_K_M |
| Local model file size | 1,929,912,432 bytes |
| Reported context length | 32,768 tokens |
| Planned application context | 4,096 tokens initially |

### Smoke-test results

1. An ordinary temperature-zero request returned the exact requested text `QWEN_READY`.
2. The first schema-constrained request returned valid JSON but omitted the explicit Critical-priority filter. It correctly translated unresolved into Open or Escalated.
3. A refined prompt that required preservation of every user constraint and supplied the relevant example returned the correct structured request: count tickets where priority equals Critical and status is Open or Escalated.

| Measurement | Result |
|---|---:|
| First ordinary request, including cold model load | 13.78 seconds |
| Initial structured request | 9.41 seconds |
| Refined correct structured request | 11.65 seconds |

These are smoke-test measurements on one machine, not final application benchmarks. The result establishes that the chosen model can produce the required structured output locally. It also establishes that JSON-schema validity alone is insufficient: the application must add explicit prompt examples, semantic validation, deterministic execution, and evaluation against held-out questions.

## Current PLAN.md status through Step 21

- Steps 1–10 are complete: checklist, deadline/machine record, Qwen feasibility,
  modular structure, strict ingestion, transactional SQLite, shared date handling,
  typed analytics requests, parameterized execution, and deterministic formatting.
- Steps 11–13 are complete: 80 overdue findings, the 48.15-hour IQR fence with 21
  long-resolution findings, and 28 preserved source timing inconsistencies. All rules
  return unique tickets with per-rule counts and combined reasons.
- Steps 14–16 are complete: compact schema-constrained prompts, semantic validation,
  one corrective retry, clarification/unsupported outcomes, distinct model failures,
  a 4,096-token context, 512-token response allowance, and a 60-second total budget.
- Steps 17–18 are complete: direct HTTP contracts expose outcome, evidence, matching
  count, pagination, reference data and timing; health and anomalies remain usable
  during model failure.
- Steps 19–20 are complete: the API-only Streamlit UI provides question submission,
  samples, reference and paging controls, result evidence, interpretation details,
  three anomaly rules, thresholds, reasons, warnings, and empty states.
- Step 21 is complete: `python run.py` validates data and ports, reuses or starts local
  Ollama, verifies `qwen2.5:3b`, starts FastAPI then Streamlit, prints both addresses,
  and stops only launcher-owned processes. The final isolated-port run reached ready
  status, returned all 28 data-quality findings, and released both ports on Ctrl+C.

Latest verification: 205 deterministic/integration tests passed, Ruff and dependency
checks passed, and all 32 live `qwen2.5:3b` tests passed in 120.05 seconds.

## Step 22 diagnostics status

Step 22 is complete. Every API request receives an `X-Request-ID` and one concise
local JSON record containing outcome, model latency, total latency, corrective retry
count, validation-error count/categories, HTTP status, and stable failure code. Tests
confirm that questions, prompts, model output, and ticket data are absent from logs.
The real launcher smoke test correlated both an HTTP 422 failure and a successful
Qwen query; the latter recorded 18,477.620 ms model latency and 18,534.037 ms total
latency before the launcher shut down cleanly.

## Steps 23 and 24 deterministic verification

Steps 23 and 24 are complete. An independent standard-library calculation over the
checksum-verified CSV reproduces all ten planned results. Application tests separately
verify the same analytics/anomaly outputs and every listed boundary: files/headers,
duplicates, numeric validation, null rules, empty results, absent ratings, exact 12-
and 24-hour thresholds, future tickets, calendar boundaries, ranking ties, combined
anomaly reasons, insufficient baselines, and idempotent ingestion. See
[DETERMINISTIC_VERIFICATION.md](DETERMINISTIC_VERIFICATION.md).

## Step 25 Qwen evaluation

Step 25 is complete. The expanded 39-case benchmark labels expected interpretation
and independently calculated answer evidence for five assessment samples and 34
additional cases. Thirty cases are outside the exact prompt examples. The final
`qwen2.5:3b` run passed 39/39 cases: 100% interpretation correctness, supported
answer correctness, assessment-sample correctness, non-example-case correctness,
clarification behavior, and invalid/prompt-injection safe handling, with no execution
failures. Mean end-to-end latency was 4,394.6 ms and P95 was 7,666.4 ms.

The first untuned run is preserved and reported honestly: it passed 25/32 overall and
22/27 supported answers. General semantic guardrails were then added and covered by
offline tests before the unchanged benchmark was rerun. See [QWEN_EVALUATION.md](QWEN_EVALUATION.md),
[QWEN_EVALUATION_INITIAL.md](QWEN_EVALUATION_INITIAL.md), and the machine-readable
artifacts in `evaluation/`.

## Steps 26 and 27 application and README verification

Steps 26 and 27 are complete. The final whole-application run submitted the open-ticket
question from the real Streamlit browser interface, reached local Qwen, and displayed
111; a direct FastAPI request in the same session returned the same value and matching
count. Mocked failure and complete-pagination coverage passed in the 42-test focused
API/UI/launcher suite. Ctrl+C released both isolated ports.

A newly created Python 3.11 environment installed `requirements.txt`, passed all 196
offline tests, Ruff and `pip check`, started FastAPI and Streamlit, returned ready/500
rows and HTTP 200, and released both clean-run ports on shutdown. The evaluator README
now contains every Step 27 item, including the exact machine, model digest and weights
blob, Qwen Research License attribution and upstream sources. See
[END_TO_END_VERIFICATION.md](END_TO_END_VERIFICATION.md).

## Steps 28 and 29 walkthrough and repository audit

Step 28 is complete. [WALKTHROUGH.md](WALKTHROUGH.md) provides an exact 30-minute
schedule, live queries with expected evidence, model and storage design explanations,
failure handling, tradeoffs, limitations, production scaling, likely evaluator
questions and a presenter checklist.

The local Step 29 content audit passes across the complete candidate file set. It
confirms required source/data, exact dependency pins, the source checksum, file-size
limits, absence of publishable environments/caches/databases/logs/model weights and
absence of high-confidence credential patterns. The suite now passes 198 offline tests.

The audited commit was published to the public repository
`https://github.com/Ansh1707/ai-customer-ticket-support`. An unauthenticated GitHub API
request confirmed public visibility and default branch `main`; an unauthenticated raw
README download matched the local checksum, and local `HEAD` matched `origin/main`.
