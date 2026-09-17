# AI Engineer Assessment Requirements Checklist

This checklist converts the assessment brief into implementation and verification items. It is the source of truth for deciding whether the project is ready to submit. Update the status and evidence columns during implementation; do not mark an item complete until its verification passes.

Status values: `NOT STARTED`, `IN PROGRESS`, `BLOCKED`, `PASS`, `FAIL`, `MANUAL`.

## Requirement interpretation

- The problem statement explicitly requires a REST API **and** a minimal UI. The deliverables section later says API **or** UI. The project will implement both because that satisfies the stricter requirement.
- The selected LLM is the locally run `qwen2.5:3b` model through Ollama.
- The LLM will interpret natural-language questions. Validated Python and SQLite logic will calculate results so numerical answers can be tested and reproduced.
- The supplied CSV is the only required dataset. Its original contents must remain unchanged.
- The assessment duration is 48 hours from receipt of the assessment document, not from the beginning of implementation.

## Core functionality

| ID | Requirement | Planned implementation | Verification and acceptance evidence | Status |
|---|---|---|---|---|
| F-01 | Ingest `support_tickets.csv`. | Validate the file and load all valid rows into a typed SQLite table. | Supplied CSV produces exactly 500 unique database rows; repeated import is reused and simulated failure rolls back completely. | PASS |
| F-02 | Make the ticket data queryable. | Provide a read-only analytics layer over SQLite with validated filters, aggregations, grouping, ordering and pagination. | Parameterized read-only executor passes supplied-data, empty-result, null, pagination, injection-shaped input and tie tests. | PASS |
| F-03 | Answer natural-language questions about the data. | Use Qwen to convert a question into a validated structured analytics request; execute it deterministically. | Expanded live orchestration covers the five assessment questions plus negation, paraphrases, multiple numeric filters, exact ratings, top-N rankings, grouped results and explicit date ranges. | PASS |
| F-04 | Use an LLM for natural-language understanding. | Call local Ollama with model `qwen2.5:3b`, temperature 0 and a schema-constrained response. | Two-stage schema-constrained client passed the 32-test live suite and final 39-case evaluation; readiness identifies the installed model and Ollama version. | PASS |
| F-05 | Detect and flag abnormally long resolution times. | Apply a documented IQR-based rule to resolved-ticket `resolution_time_hrs` values. | Type-7 quartile test verifies Q1 6.15, Q3 22.95, 48.15-hour fence and 21 explained findings. | PASS |
| F-06 | Detect and flag unresolved high-priority tickets older than 24 hours. | Flag Open or Escalated tickets with High or Critical priority whose age is greater than 24 hours at the selected reference time. | Strict boundary and future-date tests pass; default snapshot returns 80 explained findings at the visible reference. | PASS |
| F-07 | Expose the system through a REST API. | Build FastAPI endpoints for health, natural-language query and anomaly detection. | Direct HTTP tests cover all three endpoints; OpenAPI lists and constrains `/health`, `/query` and `/anomalies`; a live API query passed against Qwen. | PASS |
| F-08 | Expose the system through a minimal UI. | Build a Streamlit interface for questions, results, model status, reference time and anomaly review. | Automated component tests cover the 111-ticket query plus the three-rule, 129-ticket anomaly workflow with results matching the API. | PASS |
| F-09 | Handle evaluator questions beyond the provided examples. | Support validated counts, lists, filters, averages, rankings, grouping and explicit or relative time filters. | Five held-out live questions covering multi-value filters, lists, means, grouped ranking and relative dates passed against Qwen; results are recorded in `docs/QUERY_ORCHESTRATION.md`. | PASS |

## REST API acceptance contract

| ID | Requirement | Planned interface | Verification and acceptance evidence | Status |
|---|---|---|---|---|
| A-01 | Health check endpoint. | `GET /health` reports application, dataset, Ollama and model readiness. | Returns HTTP 200 when ready and when degraded; tests verify unavailable model and missing-dataset states. | PASS |
| A-02 | Natural-language query endpoint. | `POST /query` accepts a question, optional reference time, limit and offset and returns outcome, answer, result data, interpretation, warnings, matching count and timing. | Valid request returns 111 with typed evidence and measured timing; API pagination overrides are tested; unavailable model, missing model, invalid output and timeout errors are distinct. | PASS |
| A-03 | Anomaly endpoint. | `GET /anomalies` accepts optional rule, period, reference time and pagination controls. | Tests verify the weekly TKT-108 result, 80 overdue tickets, default time-field behavior, reference selection and paging bounds. | PASS |
| A-04 | Validate public inputs and outputs. | Use Pydantic request and response models with bounded question length and result limits. | OpenAPI exposes the 2000-character question limit and endpoint schemas; invalid bodies, extra fields and bad parameter combinations return safe 422 responses. | PASS |
| A-05 | Preserve deterministic functionality during model failure. | Keep health and anomaly computation usable when Ollama is unavailable; reject only NL queries that need the model. | HTTP integration test forces an Ollama outage: `/query` returns 503 while `/health` and `/anomalies` remain usable. | PASS |

## Minimal UI acceptance contract

| ID | Requirement | Planned interface | Verification and acceptance evidence | Status |
|---|---|---|---|---|
| U-01 | Allow users to ask questions. | Question input, submit action and sample-query controls. | All five assessment samples are selectable; component and live visual tests submit the open-ticket question successfully. | PASS |
| U-02 | Display answers and supporting data. | Show concise answer, result table, interpreted filters, warnings and pagination state. | Component and visual checks show the 111 answer, evidence metric, typed tables, interpretation expander and paging captions. | PASS |
| U-03 | Display and filter anomalies. | Anomaly rule filter, reference-time control, counts and explainable ticket table. | Component and HTTP checks cover rule/date/reference/paging controls, 129 unique tickets, 21/80/28 rule counts, ticket rows and documented thresholds. | PASS |
| U-04 | Make time interpretation visible. | Display dataset, current and custom reference-time options. | All three reference modes are available; result renderers show the chosen clock and applied half-open date range. | PASS |
| U-05 | Show service readiness and errors. | Display API, data and model state with actionable messages. | Sidebar visual QA shows all readiness states; automated tests verify structured model failures render without crashing. | PASS |
| U-06 | Use the API as the backend. | Streamlit calls FastAPI instead of reimplementing analytics. | `TicketAPIClient` is the UI's only data boundary; request-contract tests and live visual outputs match FastAPI. | PASS |

## Dataset and correctness requirements

| ID | Requirement | Planned handling | Verification and acceptance evidence | Status |
|---|---|---|---|---|
| DATA-01 | Use the supplied UTF-8 CSV with 500 rows. | Read the original file from a configurable path and preserve it unchanged. | Pre- and post-run checksum matches; validation reports 500 source rows. | PASS |
| DATA-02 | Use the actual ten-column schema. | Map `ticket_id`, `created_at`, `category`, `priority`, `status`, `response_time_hrs`, `resolution_time_hrs`, `agent_id`, `customer_rating`, and `issue_summary`. | Schema validation rejects missing, duplicate or unexpected fields with a clear error. | PASS |
| DATA-03 | Enforce documented categorical values. | Validate category, priority and status against their documented values. | Unit tests cover valid and invalid values. | PASS |
| DATA-04 | Preserve meaningful nulls. | Keep unresolved resolution time and customer rating as null rather than zero. | Tests show unresolved rows remain null and status-dependent null rules are enforced. | PASS |
| DATA-05 | Preserve source inconsistencies. | Do not repair suspicious source values silently; surface data-quality warnings and explainable anomaly flags. | The 28 records where resolution time is less than response time remain unchanged, are reported at ingestion and are queryable as deduplicated anomaly flags. | PASS |
| DATA-06 | Define historical and relative dates honestly. | Use a visible reference clock; document that the snapshot cannot reconstruct past status. | Shared date tests pass; API responses expose clocks/ranges/warnings, and the UI displays all reference modes plus the snapshot-history limitation. | PASS |
| DATA-07 | Make rankings and averages auditable. | Return contributing record counts, deterministic tie behavior and the applied date field. | Tests cover tied ranking boundaries, missing ratings, contributing counts and inferred resolution timestamps. | PASS |
| DATA-08 | Regress exact supplied-file facts independently. | Calculate the ten Step 23 acceptance values directly from the checksum-verified raw CSV without application analytics code. | Standard-library regression calculations reproduce 111/173/31 counts, rating/ranking results, March leader, 21/28/80 anomaly counts and 34 Critical elapsed tickets. | PASS |
| DATA-09 | Evaluate Qwen on a separate labeled set. | Store expected interpretations and independently calculated answers for samples, paraphrases, filters, rankings, dates, search, anomalies, ambiguity, unsupported requests and injection. | The final 39-case run passed 39/39, including all 30 cases outside exact prompt examples, with zero execution failures; baseline and final reports are retained. | PASS |

## Required sample-query coverage

| ID | Assessment query | Required capability | Verification | Status |
|---|---|---|---|---|
| Q-01 | How many tickets are currently open? | Status filter plus count. | Executor returns 111, matching an independent CSV calculation. | PASS |
| Q-02 | Which agent resolved the most tickets this month? | Inferred resolution date, monthly filter, grouping, ranking and tie handling. | At the default April 1–5 range, executor returns AGT-07 with 1; March returns AGT-01 with 16. Both match independent calculations. | PASS |
| Q-03 | Show me all Critical tickets not resolved within 12 hours. | Priority filter plus resolved-duration and unresolved-age logic. | Derived elapsed-duration query returns the independently verified 34 rows and states the reference time. | PASS |
| Q-04 | What is the average customer rating for Technical category tickets? | Category filter, null-safe average and sample count. | Executor returns 3.7403846153846154 from 104 non-null ratings, matching an independent calculation. | PASS |
| Q-05 | Are there any anomalies in resolution times this week? | Weekly date interpretation plus long-resolution anomaly rule. | April 1–5 result reports the global 48.15-hour fence and flags TKT-108 at 119.7 hours. | PASS |

## Technical constraints and operational requirements

| ID | Requirement | Planned implementation | Verification and acceptance evidence | Status |
|---|---|---|---|---|
| T-01 | Use Python only. | Implement application code, API, UI, ingestion, analytics and launcher in Python. | All authored application, API, UI, analytics, tests and startup code is Python; HTML is served only by Streamlit's installed runtime. | PASS |
| T-02 | Use no paid API or service. | Run Qwen locally through Ollama and use local SQLite. | Implemented interpretation calls only local Ollama and requires no API key; analytics use local SQLite. | PASS |
| T-03 | Allow zero-cost local evaluation. | Document local prerequisites, model download, environment setup and startup. | README documents Python/Ollama/Qwen setup and one-command startup; the same commands passed the isolated clean-environment rehearsal without paid services. | PASS |
| T-04 | Start the system with one command. | Provide `python run.py` after one-time dependency and model setup. | Real lifecycle test reused 500 rows, reached ready FastAPI and Streamlit endpoints, and Ctrl+C stopped both child process groups with both ports released. | PASS |
| T-05 | Provide dependency specification. | Supply evaluator-facing `requirements.txt` with tested, pinned versions. | A new Python 3.11 environment installed all exact direct pins; the latest working-tree run passes 205 normal tests, the clean rehearsal passed its complete suite, all 32 live tests pass, and `pip check` passes. | PASS |
| T-06 | Handle errors cleanly. | Validate inputs and distinguish data, model, timeout and internal failures. | API failure paths have stable codes without tracebacks; UI tests verify connection, model, timeout-shape and invalid-response messages render without crashing. | PASS |
| T-07 | Keep code clean and modular. | Separate configuration, ingestion, storage, LLM interpretation, analytics, anomalies, API, UI and startup concerns. | Final module-boundary review and Ruff checks passed from both working and clean environments; API-only UI and deterministic/model boundaries remain separated. | PASS |
| T-08 | Provide practical local diagnostics. | Correlate requests with concise local logs containing outcomes, timing, retries and validation categories without logging content. | API integration tests verify `X-Request-ID` correlation, success/failure records, model/total latency, retry/error counters, stable error codes and absence of question/model content. | PASS |

## Repository deliverables

| ID | Required repository item | Required contents | Verification and acceptance evidence | Status |
|---|---|---|---|---|
| R-01 | Working system. | All core functionality, API and UI requirements above. | Acceptance passed ingestion, 205 normal tests, 32 live Qwen tests, the 39-case Qwen benchmark, a real Streamlit-to-Qwen query, API/UI equivalence, clean startup and shutdown. | PASS |
| R-02 | `README.md`. | Setup, architecture overview, model and tools, example queries with actual outputs, known limitations, tests and troubleshooting. | README contains all 14 Step 27 items, including tested hardware, exact model digests, Qwen Research License/source attribution, actual outputs and measured evaluation latency; its contract test passes. | PASS |
| R-03 | `requirements.txt` or equivalent. | Tested runtime dependencies with reproducible versions. | Conventional `requirements.txt` contains exact tested direct versions and installed successfully in a new Python 3.11 environment. | PASS |
| R-04 | GitHub repository. | Source, configuration examples, tests, README and permitted dataset artifacts; no secrets or generated noise. | Public repository `https://github.com/Ansh1707/ai-customer-ticket-support` was verified through unauthenticated GitHub API and raw-file requests; local `HEAD` matches `origin/main`. | PASS |
| R-05 | Example outputs. | Capture outputs from the final implementation rather than inventing them in advance. | README includes the five live-verified assessment outputs and summarizes the held-out evaluation. | PASS |
| R-06 | Known limitations. | Explain snapshot dates, unavailable status history, local-model limits, expected scope and hardware-dependent latency. | README documents snapshot history, inferred dates, global baseline, compact-model behavior, local latency, supported scope and localhost-only security posture. | PASS |

## Evaluation-quality gates

| ID | Criterion and weight | Required quality evidence | Status |
|---|---|---|---|
| E-01 | Functionality — 30% | Demonstrate all four problem-statement capabilities through both API and UI. | Ingestion-backed health, NL analytics, long-resolution anomalies and overdue high-priority anomalies are exposed through the tested API and UI workflows. | PASS |
| E-02 | Architecture and design — 25% | Document component choices, data flow, trust boundaries and reasons for deterministic calculation. | README includes a system flow diagram, module boundaries, Qwen trust boundary, deterministic execution rationale, date semantics and anomaly definitions. | PASS |
| E-03 | Code quality — 20% | Modular code, meaningful names, validation, error handling, automated tests and clean checks. | Ruff, compilation, 205 deterministic/integration tests, 32 live tests, dependency checks, privacy-safe diagnostics, repository publication audit and process cleanup all pass. | PASS |
| E-04 | LLM integration quality — 15% | Structured prompt and output, validation, retry policy, ambiguity handling, injection resistance and live-model evaluation. | Two-stage routing/extraction, deterministic constraint preservation, one corrective retry, typed failures, 32 live tests and the final 39/39 labeled evaluation are documented and passing. | PASS |
| E-05 | README and documentation — 10% | Reproducible setup, architecture explanation, real examples and honest limitations. | Evaluator-facing README and linked design documents cover reproducible operation, verified evidence, troubleshooting and limitations. | PASS |

## Submission and walkthrough checklist

These items require the candidate to perform or confirm them manually.

| ID | Manual action | Evidence to retain | Status |
|---|---|---|---|
| M-01 | Confirm the assessment receipt timestamp and calculate the exact 48-hour deadline. | Received September 16, 2026 at 18:30 IST; deadline September 18, 2026 at 18:30 IST. | PASS |
| M-02 | Create or confirm the GitHub repository and its visibility/access. | Public GitHub API reports `public`/`main`; unauthenticated raw README checksum matches local; local and remote commit IDs match. | PASS |
| M-03 | Run the final clean-install rehearsal on the target Mac. | A new Python 3.11 environment installed the pinned file, passed all normal/live tests, and started/stopped both services successfully. | PASS |
| M-04 | Confirm no secrets, local environments, model files, databases or unnecessary logs are committed. | Staged 72-file audit passed; ignored `.venv`, caches, `.DS_Store`, runtime database and bytecode were excluded, and both staged/worktree dataset checksums match. | PASS |
| M-05 | Email the GitHub link to `RajathKumar@dotmappers.in`. | Sent-email record. | MANUAL |
| M-06 | Use subject `[AI Engineer Assessment] — Your Name`. | Sent-email subject. | MANUAL |
| M-07 | Prepare for the 30-minute architecture walkthrough. | Timed `docs/WALKTHROUGH.md` covers architecture, live evidence, failures, tradeoffs, limitations, improvements, scaling and likely questions. | PASS |

## Step 1 completion check

- [x] All four problem-statement capabilities have implementation and verification entries.
- [x] REST API, minimal UI and three named endpoint requirements are captured.
- [x] LLM, Python-only, zero-cost and single-command constraints are captured.
- [x] Dataset schema and required sample queries are captured.
- [x] Repository, README, dependency and GitHub deliverables are captured.
- [x] Evaluation weights and quality evidence are captured.
- [x] Submission deadline, email and walkthrough actions are captured.
- [x] The API/UI wording conflict is recorded and resolved using the stricter requirement.
- [x] Human-only actions are separated from implementation tasks.

Step 1 is complete when this checklist exists and every assessment requirement maps to both a planned implementation and a verification method. Implementation statuses remain `NOT STARTED` until their evidence is produced.
