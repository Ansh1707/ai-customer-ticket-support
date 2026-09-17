# REST API

Step 13 exposes the completed services through FastAPI. The application factory in
`src/ticket_support_ai/api.py` supports dependency injection for repeatable tests, and
the module-level `app` is the production entry point.

## Start the API

From the repository root, with the virtual environment dependencies installed and the
runtime database already ingested:

```bash
.venv/bin/python -m uvicorn ticket_support_ai.api:app --app-dir src --host 127.0.0.1 --port 8000
```

Interactive OpenAPI documentation is then available at
`http://127.0.0.1:8000/docs`, with the raw schema at `/openapi.json`.

## Endpoints

### `GET /health`

Returns HTTP 200 in both ready and degraded states so callers can inspect each
dependency. The response includes:

- application name and version;
- dataset availability, row count, warning count and source checksum;
- Ollama service availability, configured model availability and Ollama version; and
- the default dataset-local reference timestamp.

`status` is `ready` only when the dataset, Ollama and `qwen2.5:3b` are all available.

### `POST /query`

Accepts a JSON body:

```json
{
  "question": "How many tickets are currently open?",
  "reference_mode": "dataset",
  "custom_reference": null,
  "limit": 50,
  "offset": 0
}
```

The question must contain 1–2000 characters after trimming. `reference_mode` is one
of `dataset`, `current` or `custom`. A naive dataset-local `custom_reference` is
required only for custom mode. `limit` is 1–100 and `offset` is nonnegative; they
override pagination for list, grouped and anomaly interpretations. The response
contains `outcome` (`ok`, `clarification`, or `unsupported`), the deterministic
answer, validated interpretation, typed supporting data, reference clock, warnings,
full matching count, and interpretation/execution/total timing.

Example:

```bash
curl -s http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"How many tickets are currently open?"}'
```

### `GET /anomalies`

Supports these query parameters:

| Parameter | Values and bounds | Default |
|---|---|---|
| `rule` | `all`, `long_resolution`, `overdue_high_priority`, `resolution_before_response` | `all` |
| `period` | `this_week`, `last_week`, `this_month`, `last_month` | none |
| `time_field` | `created_at`, `resolved_at`; requires `period` | rule-based |
| `reference_mode` | `dataset`, `current`, `custom` | `dataset` |
| `custom_reference` | naive dataset-local date-time; custom mode only | none |
| `limit` | 1–100 | 50 |
| `offset` | 0–1,000,000 | 0 |

When a period is provided without a time field, long-resolution and source-timing
anomalies use `resolved_at`; overdue and combined rules use `created_at`. The endpoint remains
available when Ollama is stopped because anomaly calculation is deterministic.

Example:

```bash
curl -s 'http://127.0.0.1:8000/anomalies?rule=long_resolution&period=this_week'
```

## Error contract

Expected failures return a stable envelope:

```json
{
  "error": {
    "code": "ollama_unavailable",
    "message": "Cannot connect to Ollama at http://127.0.0.1:11434.",
    "details": []
  }
}
```

| HTTP status | Meaning |
|---:|---|
| 422 | Invalid body, query parameter, question or reference-time selection |
| 502 | Ollama returned an invalid response or repeatedly invalid structured output |
| 503 | Dataset, Ollama service or configured model is unavailable |
| 504 | Local Qwen inference exceeded its configured timeout |

Responses do not expose stack traces. A model outage affects `/query`; health and
deterministic anomaly detection remain usable.

Every response includes `X-Request-ID`. The API terminal emits one matching JSON
diagnostic with outcome, model/total latency, retry count, validation categories and
stable error code. Request bodies, prompts, model responses and ticket data are not
logged; see [DIAGNOSTICS.md](DIAGNOSTICS.md).

## Verification

- 22 HTTP integration cases cover readiness, query results, custom references,
  validation, anomaly periods and pagination, dependency isolation, safe errors,
  missing data and OpenAPI coverage.
- The opt-in live API test passed `/health` and `/query` through FastAPI against the
  installed `qwen2.5:3b` model in 13.08 seconds.
- The documented Uvicorn command was started on localhost and a real-socket
  `/anomalies?rule=long_resolution&limit=1` request returned HTTP 200 with TKT-108;
  the temporary server then shut down cleanly.
