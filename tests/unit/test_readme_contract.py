"""Protect the evaluator-facing README requirements from accidental removal."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_readme_contains_every_step_27_evaluator_requirement() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    required_evidence = (
        "## What it provides",
        "### Prerequisites",
        "### Tested environment and model",
        "### One-time installation",
        "ollama pull qwen2.5:3b",
        "python run.py",
        "http://127.0.0.1:8501",
        "## Architecture",
        "| Component | Responsibility |",
        "Qwen Research License Agreement",
        "357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b",
        "## Data and date semantics",
        "## Anomaly rules",
        "## Try the assessment questions",
        "## Testing",
        "51-case Qwen development/regression evaluation",
        "### Acceptance checklist and scope",
        "it does not establish correctness for arbitrary wording",
        "## Troubleshooting",
        "## Known limitations",
    )
    missing = [item for item in required_evidence if item not in readme]

    assert missing == []


def test_readme_measurements_match_the_current_evaluation_artifact() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    report = json.loads(
        (PROJECT_ROOT / "evaluation/qwen_eval_results.json").read_text(encoding="utf-8")
    )
    metrics = report["metrics"]

    assert f"`{report['generated_at']}`" in readme
    assert f"{metrics['latency_ms']['mean']:,.1f} ms mean end-to-end latency" in readme
    assert f"{metrics['latency_ms']['p95']:,.1f} ms P95" in readme
