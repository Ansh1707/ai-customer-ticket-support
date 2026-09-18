# Project Structure

The project uses a `src` layout so application imports are separated from repository
files. Each completed module has one primary responsibility.

```text
AI Customer Ticket Support/
├── data/
│   └── runtime/                 Generated databases and runtime state
├── docs/
│   ├── PROJECT_STRUCTURE.md     Module boundaries and structure
│   ├── SETUP_VERIFICATION.md    Machine and Qwen smoke-test evidence
│   ├── WALKTHROUGH.md           Timed 30-minute evaluator presentation script
│   └── END_TO_END_VERIFICATION.md  Whole-application and clean-run evidence
├── scripts/
│   ├── audit_repository.py      Final publication-content audit
│   └── evaluate_qwen.py         Repeatable labeled model evaluation
├── src/
│   └── ticket_support_ai/
│       ├── __init__.py          Package identity
│       ├── config.py            Settings and environment configuration
│       ├── schemas.py           Validated shared data contracts
│       ├── ingestion.py         CSV validation and ingestion
│       ├── database.py          SQLite schema and connections
│       ├── dates.py             Reference-time and period logic
│       ├── analytics.py         Deterministic query execution
│       ├── anomalies.py         Anomaly rules and explanations
│       ├── llm.py               Ollama and structured interpretation
│       ├── query.py             Query orchestration and answer formatting
│       ├── api.py               FastAPI application
│       ├── ui.py                Streamlit application
│       └── launcher.py          Preflight, startup and process supervision
├── tests/
│   ├── unit/                    Pure deterministic tests
│   ├── integration/             API and component integration tests
│   └── live/                    Explicit live-Qwen tests
├── .gitignore
├── README.md                    Evaluator setup and system guide
├── run.py                       Single-command evaluator entry point
├── REQUIREMENTS_CHECKLIST.md
├── requirements.txt
└── support_tickets.csv
```

## Dependency direction

- `config` and `schemas` are shared foundations and must not import API or UI modules.
- `ingestion`, `database`, `dates`, `analytics`, `anomalies`, and `llm` contain application services.
- `api` composes the service modules and defines public HTTP contracts.
- `ui` calls the FastAPI service and must not duplicate analytics or anomaly logic.
- Unit tests avoid external services. Integration tests mock Ollama when repeatability matters. Live tests call the installed local model only when explicitly selected.
- Generated databases and logs belong under `data/runtime` and are excluded from Git.

CSV validation is implemented in `ingestion.py`, atomic SQLite snapshot storage is
implemented in `database.py`, and shared reference-clock behavior is implemented in
`dates.py`. `schemas.py` owns the typed data, analytics-request contracts and result
models. `analytics.py` converts validated requests into parameterized read-only SQLite
queries. `anomalies.py` applies the documented IQR and overdue high-priority rules and
returns explainable, paginated findings. `config.py` owns validated Ollama settings,
and `llm.py` performs two-stage schema-constrained Qwen interpretation, reconciles
explicit text once under documented precedence, and compiles compact semantic plans
into the strict request contract. Semantic `result_limit` remains separate from the
transport `limit` and `offset` applied in `query.py`. That module also resolves the
reference clock, routes validated requests to deterministic engines and formats typed
results without asking the model to calculate or narrate them. `api.py` exposes these
services through validated FastAPI health, query and anomaly contracts with typed,
safe failure responses. `ui.py` calls only those public endpoints and renders service
readiness, natural-language answers, supporting data, reference semantics and
explainable anomaly controls in Streamlit. `launcher.py` prepares the snapshot, starts
and supervises both services, and performs bounded process-group cleanup; root
`run.py` makes that lifecycle available without installing the package.
