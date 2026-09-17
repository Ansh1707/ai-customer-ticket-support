# End-to-End Application Verification

Steps 26 and 27 were verified on September 17, 2026 using the machine and model
identified in the README. The source CSV SHA-256 remained
`812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff`.

## Real Streamlit-to-Qwen demonstration

The one-command launcher started FastAPI on isolated port 8896 and Streamlit on 8897.
The browser showed the API, 500-row dataset, Ollama and `qwen2.5:3b` as ready. From
Streamlit, the assessment question **“How many tickets are currently open?”** was
submitted with the dataset reference clock. The visible result was:

- answer: `111 tickets match the interpreted request.`
- outcome: `ok`
- matching results: `111`
- displayed total timing: 3,684.5 ms
- displayed interpretation timing: 3,673.5 ms
- displayed execution timing: 1.4 ms

A direct FastAPI request made during the same launcher session returned outcome `ok`,
aggregate value `111`, and matching count `111`. This verifies that the UI and direct
API agree while using the actual local model and database.

Ctrl+C stopped both launcher-owned processes. Ports 8896 and 8897 were probed after
shutdown and were released.

## Clean-environment rehearsal

A fresh virtual environment was created outside the repository with CPython 3.11.12.
`python -m pip install -r requirements.txt` installed the exact direct pins. From that
environment:

- 205 deterministic and integration tests passed; 32 live tests were skipped by
  default;
- Ruff passed over the repository;
- `pip check` reported no broken requirements;
- `python run.py --help` loaded successfully;
- `python run.py --api-port 8898 --ui-port 8899` reused the validated 500-row snapshot;
- the launcher confirmed `qwen2.5:3b` through Ollama 0.34.1;
- FastAPI health returned `ready`, 500 rows and the required model;
- Streamlit returned HTTP 200; and
- Ctrl+C stopped the application and released ports 8898 and 8899.

## Automated coverage

The focused API, Streamlit and launcher suite passed 42 tests. It verifies mocked
model responses, structured Ollama failures, UI/API request equivalence, public
pagination, health behavior, launcher commands, process-group shutdown and port
validation. The separately marked live suite passed 32/32 against local Qwen, and the
expanded benchmark passed 39/39.

## Reproduction

```bash
python -m pytest -q
RUN_LIVE_OLLAMA=1 python -m pytest -q tests/live -s
python scripts/evaluate_qwen.py
python run.py
```

Open `http://127.0.0.1:8501`, submit the first assessment sample, verify the answer is
111, and press Ctrl+C in the launcher terminal when finished.
