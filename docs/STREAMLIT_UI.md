# Streamlit User Interface

Step 14 provides a minimal Streamlit interface over the public FastAPI contract. The
UI contains no analytics, anomaly, date or model logic. `TicketAPIClient` calls
`/health`, `/query` and `/anomalies`, and renders the typed responses.

## Start the interface

Start the API in one terminal:

```bash
.venv/bin/python -m uvicorn ticket_support_ai.api:app --app-dir src --host 127.0.0.1 --port 8000
```

Start Streamlit in another terminal:

```bash
.venv/bin/python -m streamlit run src/ticket_support_ai/ui.py --server.address 127.0.0.1 --server.port 8501
```

Open `http://127.0.0.1:8501`. If the API uses another address, set an absolute local
URL before starting Streamlit:

```bash
export TICKET_API_BASE_URL=http://127.0.0.1:9000
```

The completed launcher combines both services with `python run.py`.

## Interface behavior

### Service status

The sidebar shows API, dataset, Ollama and model readiness, the 500-row dataset count,
and the 28 preserved source-quality warnings. A degraded dependency produces an
actionable message while leaving controls visible for retry.

### Ask the dataset

- All five assessment questions are available as sample controls.
- The editable question is limited to 2,000 characters.
- Dataset, current and custom reference clocks are available.
- Page size and offset controls apply to list and grouped results.
- Answers show warnings, the exact reference clock and any applied date range.
- Answers expose the outcome, full matching count, and measured server timing.
- Count, aggregate, grouped and ticket-list results have purpose-specific displays.
- The validated interpreted request is available in an expander for auditability.
- Questions routed to anomaly detection use the same explainable anomaly display.

The UI explicitly says that the source is a current-status snapshot and cannot
reconstruct historical status changes.

### Review anomalies

Users can choose the anomaly rule, date period, date field, reference clock, page size
and offset. Results show unique ticket counts, the per-rule breakdown, ticket details,
combined rule explanations, the IQR baseline, the 24-hour threshold, pagination state,
the reference clock and any applied date range.

## Failure handling

The HTTP client distinguishes connection, timeout, structured API and malformed JSON
failures. The page presents their safe messages without a traceback and preserves the
remaining controls. Because the anomaly tab calls the deterministic endpoint directly,
it remains usable when Ollama is down.

## Verification

- Eight automated UI tests cover request serialization, structured errors, malformed
  responses, configuration validation, query interaction, anomaly interaction,
  supporting evidence and non-crashing model failure.
- Streamlit's component test runtime verified the page without a browser or server.
- Visual QA used the running local API and actual Streamlit server. The page showed
  500 rows and ready `qwen2.5:3b`, returned 111 for the open-ticket question, and
  displayed all anomaly rule counts, supporting rows, thresholds and the reference
  clock. The current complete dataset contains 129 unique findings: 21
  long-resolution, 80 overdue high-priority and 28 source timing inconsistencies.
