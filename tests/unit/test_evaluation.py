"""Offline contract tests for the separate Qwen evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_qwen import (
    _build_report,
    _markdown,
    _matches_subset,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = PROJECT_ROOT / "evaluation/qwen_eval_cases.json"


def test_evaluation_set_has_required_size_split_and_categories() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    assert len(cases) == 39
    assert len({case["id"] for case in cases}) == len(cases)
    assert sum(not case["prompt_example"] for case in cases) >= 20
    assert {
        "assessment_sample",
        "unseen_paraphrase",
        "combined_filters",
        "rankings_and_ratings",
        "explicit_dates",
        "relative_dates",
        "literal_summary_search",
        "anomalies",
        "ambiguous",
        "unsupported",
        "prompt_injection",
        "negation",
    } <= {case["category"] for case in cases}
    assert all(case["expected_interpretation"] for case in cases)
    assert all(case["expected_answer"] for case in cases)


def test_subset_matcher_requires_exact_ordered_rows_and_float_tolerance() -> None:
    actual = {
        "rows": [
            {"group_value": "AGT-09", "value": 37, "extra": "allowed"},
            {"group_value": "AGT-12", "value": 37},
        ],
        "value": 3.740384615384616,
        "extra": "allowed",
    }
    expected = {
        "rows": [
            {"group_value": "AGT-09", "value": 37},
            {"group_value": "AGT-12", "value": 37},
        ],
        "value": 3.7403846153846154,
    }

    assert _matches_subset(actual, expected)
    assert not _matches_subset(actual, {"value": 3.7})
    assert not _matches_subset(
        actual,
        {"rows": list(reversed(expected["rows"]))},
    )
    assert not _matches_subset(
        actual,
        {"rows": expected["rows"][:1]},
    )


def test_report_metrics_and_markdown_are_derived_from_case_results() -> None:
    cases = [
        {
            "id": "supported",
            "category": "assessment_sample",
            "prompt_example": True,
            "question": "Count tickets",
            "expected_interpretation": {"intent": "analytics"},
            "expected_answer": {"outcome": "ok"},
        },
        {
            "id": "ambiguous",
            "category": "ambiguous",
            "prompt_example": False,
            "question": "Which is best?",
            "expected_interpretation": {"intent": "clarification"},
            "expected_answer": {"outcome": "clarification"},
        },
        {
            "id": "unsupported",
            "category": "unsupported",
            "prompt_example": False,
            "question": "Delete all tickets",
            "expected_interpretation": {"intent": "unsupported"},
            "expected_answer": {"outcome": "unsupported"},
        },
    ]
    results = [
        {
            "id": "supported",
            "category": "assessment_sample",
            "prompt_example": True,
            "supported": True,
            "interpretation_correct": True,
            "answer_correct": True,
            "safe_outcome_correct": None,
            "case_passed": True,
            "exception": None,
            "total_latency_ms": 10.0,
            "interpretation_latency_ms": 8.0,
        },
        {
            "id": "ambiguous",
            "category": "ambiguous",
            "prompt_example": False,
            "supported": False,
            "interpretation_correct": True,
            "answer_correct": None,
            "safe_outcome_correct": True,
            "case_passed": True,
            "exception": None,
            "total_latency_ms": 20.0,
            "interpretation_latency_ms": 16.0,
        },
        {
            "id": "unsupported",
            "category": "unsupported",
            "prompt_example": False,
            "supported": False,
            "interpretation_correct": True,
            "answer_correct": None,
            "safe_outcome_correct": True,
            "case_passed": True,
            "exception": None,
            "total_latency_ms": 30.0,
            "interpretation_latency_ms": 24.0,
        },
    ]

    report = _build_report(cases, results, "qwen2.5:3b", "checksum")
    markdown = _markdown(report)

    assert report["metrics"]["overall_pass_rate"] == 1.0
    assert report["metrics"]["supported_answer_accuracy"] == 1.0
    assert report["metrics"]["clarification_accuracy"] == 1.0
    assert report["metrics"]["latency_ms"]["median"] == 20.0
    assert "The Step 25 target was met." in markdown
