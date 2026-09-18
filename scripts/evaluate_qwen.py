#!/usr/bin/env python3
"""Run the labeled Qwen evaluation set and write JSON plus Markdown reports."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ticket_support_ai.database import ingest_csv_snapshot
from ticket_support_ai.llm import OllamaInterpreter
from ticket_support_ai.query import QueryService


async def evaluate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    interpreter = OllamaInterpreter()
    readiness = await interpreter.readiness()
    if not readiness.service_available or not readiness.model_available:
        raise RuntimeError(readiness.error or "Ollama/Qwen is not ready.")

    with tempfile.TemporaryDirectory(prefix="ticket-qwen-eval-") as temporary:
        database = Path(temporary) / "tickets.db"
        ingestion = ingest_csv_snapshot(PROJECT_ROOT / "support_tickets.csv", database)
        service = QueryService(database, interpreter=interpreter)
        results = []
        for index, case in enumerate(cases, start=1):
            print(f"[{index:02d}/{len(cases)}] {case['id']}", flush=True)
            started = perf_counter()
            try:
                response = await service.query(case["question"])
            except Exception as exc:  # noqa: BLE001 - record every case failure
                results.append(
                    {
                        "id": case["id"],
                        "category": case["category"],
                        "prompt_example": case["prompt_example"],
                        "supported": case["expected_answer"]["outcome"] == "ok",
                        "interpretation_correct": False,
                        "answer_correct": False
                        if case["expected_answer"]["outcome"] == "ok"
                        else None,
                        "case_passed": False,
                        "exception": type(exc).__name__,
                        "error": str(exc),
                        "total_latency_ms": (perf_counter() - started) * 1000.0,
                    }
                )
                continue

            payload = response.model_dump(mode="json")
            interpretation_correct = _matches_interpretation(
                payload["interpretation"], case["expected_interpretation"]
            )
            outcome_correct = _matches_subset(payload, case["expected_answer"])
            supported = case["expected_answer"]["outcome"] == "ok"
            results.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "prompt_example": case["prompt_example"],
                    "supported": supported,
                    "interpretation_correct": interpretation_correct,
                    "answer_correct": outcome_correct if supported else None,
                    "safe_outcome_correct": outcome_correct if not supported else None,
                    "case_passed": interpretation_correct and outcome_correct,
                    "exception": None,
                    "actual_outcome": payload["outcome"],
                    "actual_interpretation": payload["interpretation"],
                    "actual_answer": payload["answer"],
                    "actual_matching_count": payload["matching_count"],
                    "interpretation_latency_ms": payload["timing"]["interpretation_ms"],
                    "total_latency_ms": payload["timing"]["total_ms"],
                }
            )

    return _build_report(cases, results, readiness.model, ingestion.source_sha256)


def _build_report(
    cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
    model: str,
    source_sha256: str,
) -> dict[str, Any]:
    supported = [item for item in results if item["supported"]]
    non_supported = [item for item in results if not item["supported"]]
    clarification = [item for item in results if item["category"] == "ambiguous"]
    invalid = [
        item
        for item in results
        if item["category"] in {"unsupported", "prompt_injection"}
    ]
    assessment = [item for item in results if item["category"] == "assessment_sample"]
    non_prompt_examples = [item for item in results if not item["prompt_example"]]
    latencies = [item["total_latency_ms"] for item in results]
    interpretation_latencies = [
        item["interpretation_latency_ms"]
        for item in results
        if "interpretation_latency_ms" in item
    ]

    metrics = {
        "case_count": len(results),
        "supported_case_count": len(supported),
        "prompt_example_count": sum(item["prompt_example"] for item in results),
        "non_prompt_example_count": len(non_prompt_examples),
        "overall_pass_rate": _rate(results, "case_passed"),
        "interpretation_accuracy": _rate(results, "interpretation_correct"),
        "supported_interpretation_accuracy": _rate(supported, "interpretation_correct"),
        "supported_answer_accuracy": _rate(supported, "answer_correct"),
        "assessment_sample_pass_rate": _rate(assessment, "case_passed"),
        "non_prompt_example_pass_rate": _rate(non_prompt_examples, "case_passed"),
        "clarification_accuracy": _rate(clarification, "case_passed"),
        "invalid_safe_handling_rate": _rate(invalid, "case_passed"),
        "non_supported_safe_outcome_rate": _rate(non_supported, "safe_outcome_correct"),
        "execution_failure_rate": sum(item["exception"] is not None for item in results)
        / len(results),
        "latency_ms": {
            "mean": sum(latencies) / len(latencies),
            "median": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "maximum": max(latencies),
        },
        "interpretation_latency_ms": {
            "mean": sum(interpretation_latencies) / len(interpretation_latencies),
            "median": _percentile(interpretation_latencies, 0.5),
            "p95": _percentile(interpretation_latencies, 0.95),
            "maximum": max(interpretation_latencies),
        },
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "dataset_sha256": source_sha256,
        "reference_timestamp": "2024-04-05T00:00:00",
        "metrics": metrics,
        "category_counts": dict(Counter(item["category"] for item in results)),
        "failed_case_ids": [item["id"] for item in results if not item["case_passed"]],
        "results": results,
        "cases": cases,
    }


def _matches_subset(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _matches_subset(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return False
        return all(
            _matches_subset(actual_item, expected_item)
            for actual_item, expected_item in zip(actual, expected, strict=True)
        )
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-9)
        )
    return actual == expected


def _matches_interpretation(actual: Any, expected: Any) -> bool:
    """Match expected semantics while rejecting extra list constraints."""

    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _matches_interpretation(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                any(_matches_interpretation(item, expected_item) for item in actual)
                for expected_item in expected
            )
        )
    return _matches_subset(actual, expected)


def _rate(items: list[dict[str, Any]], field: str) -> float:
    return sum(item.get(field) is True for item in items) / len(items) if items else 0.0


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]

    def percent(value: float) -> str:
        return f"{value * 100:.1f}%"

    lines = [
        "# Qwen2.5 3B Evaluation Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"Model: `{report['model']}`",
        f"Dataset SHA-256: `{report['dataset_sha256']}`",
        f"Dataset reference: `{report['reference_timestamp']}`",
        "",
        "## Measured results",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Evaluation cases | {metrics['case_count']} |",
        f"| Clearly supported cases | {metrics['supported_case_count']} |",
        f"| Cases outside exact prompt examples | {metrics['non_prompt_example_count']} |",
        f"| Overall pass rate | {percent(metrics['overall_pass_rate'])} |",
        f"| Interpretation accuracy | {percent(metrics['interpretation_accuracy'])} |",
        f"| Supported interpretation accuracy | {percent(metrics['supported_interpretation_accuracy'])} |",
        f"| Supported answer accuracy | {percent(metrics['supported_answer_accuracy'])} |",
        f"| Assessment sample pass rate | {percent(metrics['assessment_sample_pass_rate'])} |",
        f"| Non-prompt-example regression pass rate | {percent(metrics['non_prompt_example_pass_rate'])} |",
        f"| Clarification accuracy | {percent(metrics['clarification_accuracy'])} |",
        f"| Invalid/prompt-injection safe handling | {percent(metrics['invalid_safe_handling_rate'])} |",
        f"| Execution failure rate | {percent(metrics['execution_failure_rate'])} |",
        "",
        "## Latency",
        "",
        "| Measurement | Mean | Median | P95 | Maximum |",
        "|---|---:|---:|---:|---:|",
        _latency_row("End-to-end", metrics["latency_ms"]),
        _latency_row("Interpretation", metrics["interpretation_latency_ms"]),
        "",
        "## Case results",
        "",
        "| ID | Category | Prompt example | Interpretation | Answer/safe outcome | Pass | Latency ms |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    cases_by_id = {case["id"]: case for case in report["cases"]}
    for item in report["results"]:
        answer_field = (
            item.get("answer_correct")
            if item["supported"]
            else item.get("safe_outcome_correct")
        )
        lines.append(
            f"| {item['id']} | {item['category']} | "
            f"{'yes' if item['prompt_example'] else 'no'} | "
            f"{_mark(item['interpretation_correct'])} | {_mark(answer_field)} | "
            f"{_mark(item['case_passed'])} | {item['total_latency_ms']:.1f} |"
        )
    lines.extend(["", "## Failures", ""])
    failures = [item for item in report["results"] if not item["case_passed"]]
    if not failures:
        lines.append("No evaluation cases failed.")
    for item in failures:
        case = cases_by_id[item["id"]]
        lines.extend(
            [
                f"### `{item['id']}`",
                "",
                f"Question: {case['question']}",
                "",
                f"Expected interpretation: `{json.dumps(case['expected_interpretation'], sort_keys=True)}`",
                "",
                f"Actual interpretation: `{json.dumps(item.get('actual_interpretation'), sort_keys=True)}`",
                "",
                f"Expected answer evidence: `{json.dumps(case['expected_answer'], sort_keys=True)}`",
                "",
                f"Actual answer: {item.get('actual_answer') or item.get('error')}",
                "",
            ]
        )
    lines.append("")
    target_met = (
        metrics["assessment_sample_pass_rate"] == 1.0
        and metrics["invalid_safe_handling_rate"] == 1.0
        and metrics["supported_answer_accuracy"] >= 0.9
    )
    lines.extend(
        [
            "## Target assessment",
            "",
            (
                "The Step 25 target was met."
                if target_met
                else "The Step 25 target was not fully met; failures are reported above."
            ),
            "",
            (
                "The benchmark contains expected interpretations and independently "
                "checked answer evidence. Cases outside exact prompt examples are "
                "development and regression cases: prior failures may have influenced "
                "their prompts or safeguards. They are not an untouched final test set. "
                "Metrics reflect this recorded run and are not evidence of independent "
                "generalization or a guarantee of future model behavior."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _latency_row(label: str, values: dict[str, float]) -> str:
    return (
        f"| {label} | {values['mean']:.1f} | {values['median']:.1f} | "
        f"{values['p95']:.1f} | {values['maximum']:.1f} |"
    )


def _mark(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "pass" if value else "fail"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        type=Path,
        default=PROJECT_ROOT / "evaluation/qwen_eval_cases.json",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=PROJECT_ROOT / "evaluation/qwen_eval_results.json",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=PROJECT_ROOT / "docs/QWEN_EVALUATION.md",
    )
    arguments = parser.parse_args()
    cases = json.loads(arguments.cases.read_text(encoding="utf-8"))
    report = asyncio.run(evaluate(cases))
    arguments.json_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    arguments.markdown_output.write_text(_markdown(report), encoding="utf-8")
    print(f"JSON report: {arguments.json_output}")
    print(f"Markdown report: {arguments.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
