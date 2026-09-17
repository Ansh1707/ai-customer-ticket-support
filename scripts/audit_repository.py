#!/usr/bin/env python3
"""Audit the candidate repository contents before publication or submission."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DATASET_SHA256 = (
    "812984803c7e806803269aaf00da76b1adf21c6165ce58f86fd1bef20bb5ebff"
)
REQUIRED_PATHS = {
    ".gitignore",
    "README.md",
    "REQUIREMENTS_CHECKLIST.md",
    "requirements.txt",
    "run.py",
    "support_tickets.csv",
    "src/ticket_support_ai/api.py",
    "src/ticket_support_ai/ui.py",
    "tests/integration/test_api.py",
    "docs/WALKTHROUGH.md",
}
FORBIDDEN_PARTS = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
FORBIDDEN_SUFFIXES = {
    ".db",
    ".gguf",
    ".log",
    ".safetensors",
    ".sqlite",
    ".sqlite3",
}
SECRET_PATTERNS = {
    "private key": re.compile(
        rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"
    ),
    "AWS access key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "OpenAI/GitHub-style token": re.compile(rb"\b(?:sk|gh[pousr])_[A-Za-z0-9]{20,}\b"),
    "assigned credential": re.compile(
        rb"(?i)(?:api[_-]?key|password|secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
    ),
}
MAX_FILE_BYTES = 5 * 1024 * 1024


def _run_git(*arguments: str) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _run_git_bytes(*arguments: str) -> bytes:
    result = subprocess.run(
        ("git", *arguments),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout


def candidate_paths() -> list[Path]:
    """Return tracked, staged and untracked non-ignored deliverable files."""

    output = _run_git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return sorted(
        (PROJECT_ROOT / item).resolve()
        for item in output.split("\0")
        if item and (PROJECT_ROOT / item).is_file()
    )


def forbidden_reason(relative: Path) -> str | None:
    """Explain why a candidate must not be published, if applicable."""

    if any(part in FORBIDDEN_PARTS for part in relative.parts):
        return "local environment or cache"
    if relative.name == ".DS_Store":
        return "OS metadata"
    if relative.suffix.casefold() in FORBIDDEN_SUFFIXES:
        return "generated database, log, or model weights"
    if relative.parts[:2] == ("data", "runtime") and relative.name != ".gitkeep":
        return "generated runtime state"
    return None


def secret_matches(content: bytes) -> list[str]:
    """Return names of high-confidence credential patterns in file content."""

    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(content)]


def audit(*, require_remote: bool) -> list[str]:
    """Return all repository audit failures."""

    failures: list[str] = []
    paths = candidate_paths()
    relative_paths = {str(path.relative_to(PROJECT_ROOT)) for path in paths}
    missing = sorted(REQUIRED_PATHS - relative_paths)
    if missing:
        failures.append(f"missing required paths: {', '.join(missing)}")

    for path in paths:
        relative = path.relative_to(PROJECT_ROOT)
        reason = forbidden_reason(relative)
        if reason:
            failures.append(f"forbidden file {relative}: {reason}")
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            failures.append(f"oversized file {relative}: {size} bytes")
            continue
        matches = secret_matches(path.read_bytes())
        if matches:
            failures.append(f"credential pattern in {relative}: {', '.join(matches)}")

    dataset = PROJECT_ROOT / "support_tickets.csv"
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    if digest != EXPECTED_DATASET_SHA256:
        failures.append(f"dataset SHA-256 changed: {digest}")
    try:
        staged_dataset = _run_git_bytes("show", ":support_tickets.csv")
    except subprocess.CalledProcessError:
        staged_dataset = b""
    if staged_dataset:
        staged_digest = hashlib.sha256(staged_dataset).hexdigest()
        if staged_digest != EXPECTED_DATASET_SHA256:
            failures.append(f"staged dataset SHA-256 changed: {staged_digest}")

    requirement_lines = [
        line.strip()
        for line in (PROJECT_ROOT / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    unpinned = [line for line in requirement_lines if "==" not in line]
    if unpinned:
        failures.append(f"unpinned dependencies: {', '.join(unpinned)}")

    try:
        _run_git(
            "diff",
            "--check",
            "--cached",
            "--",
            ".",
            ":(exclude)support_tickets.csv",
        )
    except subprocess.CalledProcessError as exc:
        failures.append(f"staged whitespace errors: {exc.stdout or exc.stderr}")

    if require_remote:
        try:
            remote = _run_git("remote", "get-url", "origin")
        except subprocess.CalledProcessError:
            remote = ""
        if not remote:
            failures.append("origin remote is not configured")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-remote",
        action="store_true",
        help="also require a configured origin remote",
    )
    arguments = parser.parse_args()
    failures = audit(require_remote=arguments.require_remote)
    if failures:
        print("Repository audit FAILED:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Repository audit passed.")
    print(f"Candidate files: {len(candidate_paths())}")
    print(f"Dataset SHA-256: {EXPECTED_DATASET_SHA256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
