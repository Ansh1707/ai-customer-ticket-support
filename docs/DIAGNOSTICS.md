# Local Request Diagnostics

Step 22 adds one concise JSON log record for every FastAPI request. Logs are written
to the API process standard error and require no account, network service, collector,
or additional dependency.

## Correlation

Every request receives a random 32-character request identifier. The same identifier
appears in the JSON log and the `X-Request-ID` response header, including handled
error responses. This allows an evaluator to copy the header value and locate the
corresponding local record.

## Logged fields

| Field | Meaning |
|---|---|
| `timestamp` | UTC time at completion |
| `event` | Always `request_complete` |
| `request_id` | Per-request correlation identifier |
| `method`, `path`, `status_code` | HTTP operation and result |
| `outcome` | Query outcome, health state, `ok`, or `error` |
| `error_code` | Stable API error code when a handled request fails |
| `model_latency_ms` | Total time spent in Ollama chat calls for the request |
| `total_latency_ms` | Complete FastAPI request duration |
| `retries` | Corrective model calls after invalid structured output |
| `validation_errors` | Number of API or model validation failures |
| `validation_error_kinds` | Bounded categories such as `model_schema_validation` |

Example successful query log:

```json
{"event":"request_complete","method":"POST","model_latency_ms":8123.4,"outcome":"ok","path":"/query","request_id":"e33f...","retries":0,"status_code":200,"timestamp":"2026-09-17T14:40:00.000+00:00","total_latency_ms":8131.2,"validation_error_kinds":[],"validation_errors":0}
```

Example failed structured-output request:

```json
{"error_code":"invalid_model_output","event":"request_complete","method":"POST","model_latency_ms":9200.1,"outcome":"error","path":"/query","request_id":"8a91...","retries":1,"status_code":502,"timestamp":"2026-09-17T14:41:00.000+00:00","total_latency_ms":9205.0,"validation_error_kinds":["model_schema_validation"],"validation_errors":2}
```

## Privacy boundary

Diagnostics do not contain questions, prompts, model responses, filter values, ticket
rows, issue summaries, or dataset contents. Validation logs retain only a short fixed
category. Detailed user-facing validation messages remain in the HTTP response where
appropriate.

## Verification

Integration tests verify successful and failed records, response-header correlation,
retry and validation counters, timing fields, error codes, and absence of the private
question and invalid model content. A separate corrupt SQLite snapshot verifies that
health degrades cleanly and both data endpoints return correlated
`dataset_unavailable` diagnostics instead of plain HTTP 500 responses. A real launcher
run also confirms that the JSON
record is visible in the terminal used to start `python run.py`.

The final local smoke test correlated a successful Qwen request through request ID
`c4747f30779244e2b706a26774dab76f`; it logged `ok`, HTTP 200, 18,477.620 ms of model
latency, 18,534.037 ms total latency, zero retries, and zero validation errors. A
separate invalid request correlated through its response header and logged HTTP 422,
`validation_error`, one `api_request_validation` error, and no submitted content.
