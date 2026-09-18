# Local Qwen Interpretation

Step 11 implements natural-language interpretation with the locally installed
`qwen2.5:3b` model through Ollama. Qwen converts user language into a bounded semantic
plan; it never executes SQL, reads the database, or calculates an answer.

## Interpretation pipeline

The interpreter uses two schema-constrained stages:

1. A small router classifies the question as analytics, anomalies, clarification, or
   unsupported.
2. Qwen receives only the schema for that selected intent. Analytics questions use a
   compact semantic plan, which deterministic Python compiles into the strict
   `AnalyticsRequest` contract from Step 8.

This design is based on live evidence. Supplying the 3B model with one large union
schema produced valid JSON but repeatedly selected the anomaly branch for ordinary
analytics questions. Separating routing from extraction removed that branch bias.

The compact analytics plan captures categorical filters, a collection of numeric
conditions, metric, aggregation, grouping, date semantics, sorting and a semantic
result limit. Numeric equality and multiple comparisons use the same collection-based
contract; there is no narrower single-threshold compatibility path.

All detail plans pass through one reconciliation boundary before compilation. Its
precedence is explicit:

1. Literal user constraints win for values, negation, numbers, dates and requested
   result count.
2. Deterministic scope and safety rules correct unsupported or contradictory model
   structure.
3. Schema-valid Qwen choices supply semantic details the user did not state.
4. Contract defaults fill only fields still absent.

The reconciled plan is compiled once and must pass the same Pydantic validation used
by the deterministic executor. The router has one separate responsibility: selecting
the detail schema. It does not calculate filters or results. API pagination is applied
after interpretation and cannot replace the question's semantic result limit.

A semantic completeness gate then compares the compiled request with independently
extracted material cues: positive and negative categorical values, unresolved status,
every supported numeric comparison, summary-search text, date field and range, anomaly
rule, and requested result count. A mismatch returns clarification with zero query
execution instead of an `ok` answer from a partial plan. Quoted spans are masked while
extracting filter and routing cues, then recovered only as literal summary-search text;
for example, `summaries contain "resolved"` cannot create `status = Resolved`.

## Model controls

- Model: `qwen2.5:3b`
- Provider: local Ollama at `http://127.0.0.1:11434` by default
- Temperature: 0
- Seed: 0
- Context: 4,096 tokens
- Response allowance: 512 tokens per call
- Streaming: disabled
- Output: Ollama JSON schema mode
- Correction policy: one schema-validation retry per stage
- Question limit: 2,000 characters
- Total query budget: 60 seconds including correction; connection timeout: 3 seconds

The settings can be overridden with `OLLAMA_BASE_URL`, `OLLAMA_MODEL`,
`OLLAMA_CONNECT_TIMEOUT`, `OLLAMA_REQUEST_TIMEOUT`, `OLLAMA_CONTEXT_TOKENS`,
`OLLAMA_RESPONSE_TOKENS`, `OLLAMA_CORRECTIVE_RETRIES`, and `MAX_QUESTION_CHARS`.
No API key or paid service is used.

## Safety and failure handling

- User text is placed in a user message and explicitly treated as data to classify.
- Prompts prohibit SQL, code execution, invented fields and instruction replacement.
- Model output is accepted only through closed Pydantic schemas with extra fields
  forbidden.
- The model cannot provide identifiers or expressions directly to SQLite.
- Invalid output receives one correction attempt with a bounded validation summary.
- Blank or oversized questions fail before any network request.
- Connection failure, inference timeout, missing model, bad HTTP response, malformed
  response shape, and repeated schema failure have distinct exception types.
- A readiness method reports Ollama availability, installed-model availability, model
  name and Ollama version for the later health endpoint.

## Live verification

The opt-in live suite calls the installed model when `RUN_LIVE_OLLAMA=1`. The latest
complete run passed 34 interpreter, orchestration, and API checks in 138.26 seconds,
including:

- all five assessment sample questions;
- the source timing inconsistency question and its 28 deterministic findings;
- two unseen paraphrases for unresolved Critical tickets and lowest agent rating;
- ambiguous ranking routed to clarification;
- ticket deletion routed to unsupported;
- prompt-injection text routed to unsupported; and
- quoted `"resolved"` summary text preserved without adding a status filter;
- an unsupported numeric range stopped at clarification with zero execution time; and
- live readiness identifying `qwen2.5:3b` and the running Ollama version.

The normal test suite skips live calls so it remains deterministic and does not require
Ollama. Mocked tests cover request payloads, two-stage schemas, correction context,
question validation, transport failures, missing models, malformed responses and
readiness states.

## Capability boundary and module ownership

The model-facing `AnalyticsPlan` now carries typed `null_conditions` alongside numeric
conditions. Both compile to the existing engine's typed filters. The documented
unsupported statistical, Boolean and dual-date families are checked independently
of model route/output before detail generation and again at reconciliation. This
preserves a deliberately bounded contract without substituting mean for median,
count for percentage, or AND for cross-field OR.

`llm.py` owns HTTP, retries and the total timeout. `llm_prompts.py` owns prompts;
`llm_plans.py` owns compact contracts; `llm_language.py` extracts literal cues;
`llm_semantics.py` compiles and checks plans; `capabilities.py` declares limitations.
No module performs arithmetic through the LLM. See the remediation report for tests.
