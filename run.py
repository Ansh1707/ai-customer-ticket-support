"""Evaluator entry point for the complete local application."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

try:
    from ticket_support_ai.launcher import main
except ModuleNotFoundError as exc:
    missing = exc.name or "a required package"
    raise SystemExit(
        f"Missing dependency {missing!r}. Install requirements first with: "
        f"{sys.executable} -m pip install -r {PROJECT_ROOT / 'requirements.txt'}"
    ) from exc


if __name__ == "__main__":
    raise SystemExit(main(project_root=PROJECT_ROOT))
