# Single-Command Launcher

Step 15 adds the evaluator entry point required by the assessment:

```bash
python run.py
```

After one-time Python dependency and Ollama model setup, this command owns the complete
local application lifecycle.

## Startup sequence

1. Validate that the API and UI ports are available.
2. Strictly validate `support_tickets.csv` and atomically ingest it, or reuse the
   existing SQLite snapshot when the checksum and row count match.
3. Reuse a reachable Ollama service or start `ollama serve` when the executable is
   installed, then check `qwen2.5:3b`. A remaining model outage is reported with exact
   setup commands and does not prevent deterministic health and anomaly workflows.
4. Start FastAPI in its own process group.
5. Wait for a successful `/health` HTTP response before starting the UI.
6. Start Streamlit in a second process group and wait for its HTTP response.
7. Print the UI and OpenAPI addresses, then supervise both services.

If a child exits unexpectedly, startup or supervision fails with the service name and
exit code. Ctrl+C or a termination signal stops all launcher-owned process groups,
waits up to eight seconds, and force-stops only a child that did not exit.

## Default addresses

- Streamlit UI: `http://127.0.0.1:8501`
- FastAPI documentation: `http://127.0.0.1:8000/docs`
- FastAPI health: `http://127.0.0.1:8000/health`

## Options

```text
--source-csv PATH       source CSV to validate and ingest
--database PATH         generated SQLite snapshot
--api-host HOST         FastAPI bind host
--api-port PORT         FastAPI port
--ui-host HOST          Streamlit bind host
--ui-port PORT          Streamlit port
--startup-timeout SEC   per-service HTTP readiness deadline
--skip-model-check      skip only the optional pre-start Ollama check
```

The launcher passes the selected database and API address to child processes through
their private environment. It does not require a `.env` file, secrets, paid APIs or a
globally installed Python package.

## Common startup errors

- **Address unavailable:** stop the conflicting process or select alternate ports,
  for example `python run.py --api-port 9000 --ui-port 9001`.
- **Missing dependency:** install with
  `python -m pip install -r requirements.txt` using the active environment.
- **Invalid CSV:** correct or restore the supplied file; the existing database is not
  partially replaced.
- **Ollama/model warning:** install Ollama if needed, then run
  `ollama pull qwen2.5:3b`. The launcher starts the local service when possible; the
  anomaly page remains available in the meantime.

## Verification

- Launcher unit tests cover settings, atomic preparation and reuse, exact child
  commands, environment propagation, HTTP readiness order, unexpected exits,
  reverse-order termination, idempotent cleanup and invalid configuration.
- The real command was tested on isolated ports 8876 and 8877. It reused 500 rows,
  confirmed Ollama 0.34.1 and `qwen2.5:3b`, returned ready responses from FastAPI and
  Streamlit, and printed both service addresses.
- Ctrl+C produced a clean exit, both child services stopped, and neither QA port
  remained in the listening state.
