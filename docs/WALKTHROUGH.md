# 30-Minute Architecture Walkthrough

This is the presenter script for Step 28. It is designed for a 30-minute evaluator
session with a working local Ollama service and the repository already installed.

## Before the call

1. Run `ollama list` and confirm `qwen2.5:3b` is present.
2. Activate `.venv`, run `python -m pip check`, and start `python run.py`.
3. Open `http://127.0.0.1:8501` and keep `http://127.0.0.1:8000/docs` in a second tab.
4. Leave the reference selector on **Dataset reference**, page size 50 and offset 0.
5. Keep `README.md`, `docs/QWEN_EVALUATION.md`, and this script available.
6. Do not run model downloads, dependency installation or the complete test suite
   during the presentation.

## Timing plan

| Time | Segment | Outcome |
|---|---|---|
| 00:00–03:00 | Problem, requirements and dataset | Establish scope, stronger API-and-UI interpretation and verified data facts |
| 03:00–08:00 | Architecture and Qwen's role | Explain the trust boundary and deterministic calculation |
| 08:00–18:00 | Live questions and anomalies | Demonstrate required behavior, evidence and API/UI agreement |
| 18:00–23:00 | Tests and failure handling | Show repeatability, evaluation quality and degraded behavior |
| 23:00–30:00 | Tradeoffs, limitations and scaling | Defend design choices and describe a production path |

## 00:00–03:00 — Problem and dataset

Opening statement:

> This application turns a fixed 500-ticket CSV into a locally runnable analytical
> system. Qwen2.5 3B understands English questions; validated Python and SQLite
> calculate every answer. FastAPI and Streamlit expose the same backend, and no paid
> service or API key is required.

Show the README purpose and verified outputs. State these dataset facts:

- 500 unique ticket IDs and no duplicate rows;
- 327 Resolved, 111 Open and 62 Escalated tickets;
- 173 unresolved tickets and 31 unresolved Critical tickets;
- missing resolution times and ratings occur on all 173 unresolved records;
- 28 resolved rows report resolution shorter than first response and are preserved;
- the file is a current-status snapshot, with no status-change history.

Explain that the assessment says API and UI in its requirements even though a later
deliverable uses “or,” so both were implemented.

## 03:00–08:00 — Architecture and model boundary

Show the README Mermaid diagram and trace one question:

1. Streamlit sends the standalone question to FastAPI.
2. Qwen performs two schema-constrained stages: intent routing and compact plan
   extraction at temperature 0 and seed 0.
3. Pydantic and deterministic semantic safeguards reject or correct unsafe structure.
4. The analytics engine builds an allowlisted, parameterized, read-only query.
5. SQLite returns typed evidence; Python formats the answer.

Key point: Qwen never sees all 500 rows, calculates a mean, writes SQL, mutates a
ticket or constructs the final numerical claim. This makes a compact 3B model useful
without trusting it with arithmetic or execution.

### Why structured analytics fits this scope and model

The dataset has ten known columns and the requested work is filtering, counting,
aggregation, grouping, ranking and date interpretation. A bounded semantic contract
matches those operations directly. It reduces prompt size, prevents arbitrary code or
SQL, exposes interpretations for review and lets every calculation be tested without
the model.

### Why SQLite is sufficient

Five hundred rows fit comfortably in an embedded database. SQLite supplies typed
storage, transactions, indexes, parameterized queries and zero-service deployment.
Adding a database server would add setup and failure modes without improving this
assessment workload.

### Why arithmetic is deterministic

The model returns only intent and operands. Python/SQLite calculate counts, sums,
averages, quartiles, dates and rankings. The same dataset checksum and reference clock
therefore produce the same evidence, regardless of wording or model prose.

## 08:00–18:00 — Live demonstration

Use the Streamlit sample selector. Pause after each result to show the interpretation,
reference clock and supporting evidence.

| Minute | Action | Expected evidence |
|---|---|---|
| 08:00 | Ask “How many tickets are currently open?” | 111 |
| 09:30 | Ask “Which agent resolved the most tickets this month?” | AGT-07 with 1 at the April 1–5 dataset range |
| 11:00 | Ask “Show me all Critical tickets not resolved within 12 hours.” | 34 matching tickets; elapsed-time interpretation |
| 13:00 | Ask for average Technical customer rating | 3.74 from 104 ratings across 152 matched tickets |
| 14:30 | Ask for resolution-time anomalies this week | TKT-108, 119.7 hours, above 48.15-hour fence |
| 16:00 | Open Review anomalies and load all rules | 129 unique tickets; rule counts 21, 80 and 28 |
| 17:00 | Open FastAPI `/docs` or cite the direct check | Same backend contracts and result evidence |

If inference is slow, explain that the model is local on an 8 GB M1 machine and show
the already captured output in the README rather than repeatedly submitting.

## 18:00–23:00 — Tests and failures

Show the README testing section and reports rather than running long suites live:

- 196 deterministic/integration tests;
- 24/24 live-Qwen tests;
- 32/32 labeled evaluation cases, including all five assessment samples and 23 cases
  excluded from exact prompt examples;
- 5.12-second mean and 9.29-second P95 evaluation latency;
- final clean-environment install, startup and shutdown rehearsal.

Describe failure behavior:

- malformed CSV stops transactionally with row/field evidence;
- Ollama outage makes `/query` return a structured 503 while health and deterministic
  anomaly review remain available;
- schema-invalid model output receives one corrective retry, then fails safely;
- ambiguous questions ask one clarification and unsupported or injection-shaped
  requests cannot execute actions;
- request IDs correlate privacy-safe logs without recording questions or ticket data;
- pagination reports the complete matching count and retrieves stable pages.

## 23:00–30:00 — Tradeoffs, limitations and scaling

### Why an interpretable anomaly rule

The assessment dataset is small and unlabeled. Tukey's 1.5×IQR fence is deterministic,
robust to skew, easy to reproduce and gives every flag an observed value and threshold.
The overdue rule directly encodes the business condition: unresolved High/Critical
tickets strictly older than 24 hours. These rules are auditable; an opaque anomaly
model would add unvalidated behavior without labeled ground truth.

### Why historical status cannot be reconstructed

Each row contains only one current status. There are no transition events or snapshot
timestamps. Changing the reference clock can change date ranges and unresolved age,
but it cannot reveal whether a currently resolved ticket was open on an earlier date.
The application returns that limitation instead of inventing history.

### Main tradeoffs

- The compact local model keeps cost and privacy risk low but has variable latency and
  needs strict schemas and semantic guardrails.
- A global IQR baseline is transparent and stable but does not model category-specific
  service levels.
- Inferred `resolved_at` enables date analysis but depends on the supplied duration.
- Standalone questions simplify correctness; conversational references require state
  and are intentionally clarified.
- Localhost and no authentication suit the assessment, not a shared production system.

### Scaling path

For larger batch data, stream CSV chunks into PostgreSQL or a warehouse, move source
validation into a staged ingestion job, add indexes/partitions for time, status,
priority and agent, and precompute expensive aggregate or anomaly baselines. Keep the
same Pydantic semantic contract so the model remains isolated from physical storage.

For live tickets, consume append-only ticket and status events, store explicit
`resolved_at` and status history, maintain a snapshot/read model, watermark event time,
and calculate overdue work from a controlled scheduler. Add authentication, tenant
scoping, rate limits, background model workers, bounded queues, tracing, metrics and a
production database. Version anomaly policies and evaluate them against labeled
incidents before adding statistical or learned detectors.

## Likely evaluator questions

| Question | Short answer |
|---|---|
| Why not RAG or embeddings? | The task queries structured fields; semantic retrieval would make exact counts less reliable. |
| Why not give the CSV to Qwen? | It wastes context, weakens arithmetic reliability and exposes row data unnecessarily. |
| How is prompt injection contained? | User text can only populate a strict request union; execution uses allowlisted operations and parameters. |
| Why does “this month” return only one resolution? | The reproducible dataset clock is April 5 and only one inferred completion falls in April 1–5. |
| Are 32/32 results guaranteed? | No. They are one recorded temperature-zero run; the initial baseline is retained and model behavior can vary. |
| What would you improve next? | Add event history, production auth/observability, richer evaluation splits and domain-specific anomaly policies. |

## Final presenter checklist

- [ ] Rehearse once and keep the total at or below 30 minutes.
- [ ] Confirm Ollama, API, UI and model readiness before screen sharing.
- [ ] Use the dataset reference clock so results match documented evidence.
- [ ] Show at least one interpretation and one supporting-data table.
- [ ] Explain one safe failure without intentionally breaking the live demo.
- [ ] Leave seven minutes for tradeoffs and scaling rather than adding more queries.
- [ ] Keep the README and captured reports ready as a fallback.
