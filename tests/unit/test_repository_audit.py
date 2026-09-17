"""Tests for the final repository audit safeguards."""

from pathlib import Path

from scripts.audit_repository import forbidden_reason, secret_matches


def test_repository_audit_rejects_generated_and_model_files() -> None:
    assert forbidden_reason(Path(".venv/bin/python"))
    assert forbidden_reason(Path("data/runtime/tickets.db"))
    assert forbidden_reason(Path("weights/model.safetensors"))
    assert forbidden_reason(Path("debug.log"))
    assert forbidden_reason(Path("data/runtime/.gitkeep")) is None
    assert forbidden_reason(Path("support_tickets.csv")) is None


def test_repository_audit_detects_high_confidence_credentials() -> None:
    aws_fixture = b"AWS=" + b"AKIA" + b"1234567890ABCDEF"
    password_fixture = b"password" + b" = 'correct-horse-battery-staple'"

    assert secret_matches(aws_fixture) == ["AWS access key"]
    assert secret_matches(password_fixture) == [
        "assigned credential"
    ]
    assert secret_matches(b"No API key is required.") == []
