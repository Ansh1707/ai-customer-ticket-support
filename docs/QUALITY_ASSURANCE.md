# Quality Assurance and Clean-Environment Rehearsal

Step 16 freezes the tested direct dependencies and verifies the complete application
from an isolated Python environment. The assessment source CSV remained unchanged.

## Pinned environment

`requirements.txt` contains the exact direct versions used for final verification:

| Package | Version |
|---|---:|
| FastAPI | 0.141.1 |
| Uvicorn | 0.53.0 |
| Streamlit | 1.64.0 |
| Pydantic | 2.13.5 |
| pandas | 3.0.5 |
| HTTPX | 0.28.1 |
| pytest | 9.1.1 |
| Ruff | 0.16.8 |

The supported and tested interpreter is CPython 3.11.12 on Apple Silicon macOS.
SQLite is provided by Python, while Ollama and `qwen2.5:3b` remain separate local
prerequisites.

## Clean installation

A new Python 3.11 virtual environment was created outside the repository with no
access to the project `.venv`. Running the evaluator command below downloaded and
installed the pinned requirements successfully:

```bash
python -m pip install -r requirements.txt
```

`pip check` reported no broken requirements. From that isolated environment:

- Ruff passed across `src`, `tests`, and `run.py`.
- The normal suite passed 179 tests, with 22 intentionally opt-in live tests skipped.
- `run.py --help` loaded successfully, proving the entry point had no undeclared import.
- All 22 live Ollama/Qwen tests passed in 107.62 seconds.
- `run.py --api-port 8886 --ui-port 8887` started both services successfully.
- FastAPI returned ready status with 500 rows and the expected source checksum.
- Streamlit returned HTTP success.
- Ctrl+C stopped both child services and released both ports.

## Live-model coverage

The 22 live tests cover:

- Ollama readiness and installed-model detection;
- all five assessment questions at the interpretation and end-to-end query layers;
- held-out counts, filters, lists, means, grouped rankings, and relative dates;
- paraphrases, ambiguity, unsupported mutation, and instruction-injection resistance;
- FastAPI health and natural-language query behavior through the real local model.

All calculations are still independently tested without Qwen so model variability
cannot conceal incorrect analytics.

## Repository hygiene

- `.venv`, Python bytecode, pytest/Ruff caches, generated SQLite files, logs,
  `.DS_Store`, local Streamlit state and `.env` are ignored.
- The generated runtime database is absent from Git status; only its `.gitkeep` is
  eligible for version control.
- A credential-pattern scan found no embedded API keys, passwords, secrets or tokens.
- Authored runtime and test files under `src` and `tests` are Python only.
- The final CSV SHA-256 remains
  `812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff`.

## Repeatable verification commands

```bash
python -m pip check
python -m ruff check src tests run.py
python -m pytest -q
RUN_LIVE_OLLAMA=1 python -m pytest -q tests/live -s
python run.py
```

The full live suite requires Ollama to be running with `qwen2.5:3b` installed. The
normal suite remains fast and deterministic without Ollama.

After the Steps 28–29 walkthrough and repository-audit work, the suite passes 198
deterministic/integration tests and all 24 live tests in 100.64 seconds. The added
coverage includes independent raw-CSV facts, strict 12-hour elapsed boundaries, small
anomaly baselines, diagnostics, public pagination, launcher-started Ollama, and the
evaluation harness contract. The separate 32-case Qwen benchmark passed 32/32 with
23/23 held-out cases, 0 execution failures, 5.12-second mean latency, and 9.29-second
P95 latency. Its expected evidence, complete results, and initial baseline are retained
under `evaluation/` and `docs/QWEN_EVALUATION*.md`.

The final clean-environment rehearsal installed every pinned dependency again, passed
the then-current 196-test offline suite, Ruff and `pip check`, and started both application
services. A real browser submission through Streamlit reached Qwen and returned the
same 111-ticket result as the direct API. Both normal and clean-environment launcher
runs released their API and UI ports after Ctrl+C. The README contract test verifies
that the evaluator setup, model identity/license, architecture, examples, commands,
measurements, limitations and troubleshooting sections remain present.

The two additional Step 29 tests verify that the publication audit rejects local
environments, caches, databases, logs, model weights and high-confidence credential
patterns. `python scripts/audit_repository.py` passes over the complete candidate file
set and rechecks the pinned dependencies plus dataset checksum. The timed walkthrough
is retained in `docs/WALKTHROUGH.md`.
