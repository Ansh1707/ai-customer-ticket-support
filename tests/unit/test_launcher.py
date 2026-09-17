"""Tests for single-command preparation, startup, and child cleanup."""

from __future__ import annotations

import signal
from pathlib import Path

import pytest

from ticket_support_ai import launcher
from ticket_support_ai.database import read_ingestion_metadata
from ticket_support_ai.launcher import (
    ApplicationLauncher,
    LauncherError,
    LauncherSettings,
    ManagedProcess,
)
from ticket_support_ai.llm import OllamaModelStatus

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = PROJECT_ROOT / "support_tickets.csv"


class FakeProcess:
    """Minimal subprocess stand-in for command and cleanup assertions."""

    next_pid = 40_000

    def __init__(self, command, **kwargs) -> None:
        self.command = tuple(command)
        self.cwd = kwargs["cwd"]
        self.env = kwargs["env"]
        self.start_new_session = kwargs["start_new_session"]
        self.returncode: int | None = None
        self.pid = FakeProcess.next_pid
        FakeProcess.next_pid += 1
        self.wait_timeouts: list[float | None] = []

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        self.returncode = 0
        return 0

    def terminate(self) -> None:
        self.returncode = -signal.SIGTERM

    def kill(self) -> None:
        self.returncode = -signal.SIGKILL


def settings(tmp_path: Path, **updates) -> LauncherSettings:
    values = {
        "project_root": PROJECT_ROOT,
        "source_csv": SOURCE_CSV,
        "database_path": tmp_path / "tickets.db",
        "api_host": "127.0.0.1",
        "api_port": 18765,
        "ui_host": "127.0.0.1",
        "ui_port": 18766,
        "startup_timeout_seconds": 5.0,
        "check_model": False,
    }
    values.update(updates)
    return LauncherSettings(**values)


def test_settings_reject_invalid_ports_and_collisions(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="API port"):
        settings(tmp_path, api_port=0)
    with pytest.raises(ValueError, match="different"):
        settings(tmp_path, ui_port=18765)
    with pytest.raises(ValueError, match="timeout"):
        settings(tmp_path, startup_timeout_seconds=0)


def test_prepare_ingests_then_reuses_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(launcher, "_ensure_port_available", lambda *args: None)
    selected = settings(tmp_path)

    ApplicationLauncher(selected).prepare()
    first_output = capsys.readouterr().out
    ApplicationLauncher(selected).prepare()
    second_output = capsys.readouterr().out

    metadata = read_ingestion_metadata(selected.database_path)
    assert metadata.row_count == 500
    assert "500 rows ingested" in first_output
    assert "500 rows reused" in second_output


def test_prepare_starts_installed_ollama_when_service_is_unreachable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeInterpreter:
        def __init__(self) -> None:
            self.calls = 0

        async def readiness(self) -> OllamaModelStatus:
            self.calls += 1
            ready = self.calls >= 2
            return OllamaModelStatus(
                model="qwen2.5:3b",
                service_available=ready,
                model_available=ready,
                version="test" if ready else None,
                error=None if ready else "Ollama is unavailable.",
            )

    monkeypatch.setattr(launcher, "_ensure_port_available", lambda *args: None)
    monkeypatch.setattr(launcher, "OllamaInterpreter", FakeInterpreter)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/ollama")
    selected = settings(tmp_path, check_model=True)
    application = ApplicationLauncher(selected)
    spawned: list[tuple[str, tuple[str, ...]]] = []

    def fake_spawn(name, command, environment):
        del environment
        spawned.append((name, tuple(command)))
        process = FakeProcess(command, cwd=PROJECT_ROOT, env={}, start_new_session=True)
        managed = ManagedProcess(name, process)
        application.processes.append(managed)
        return managed

    monkeypatch.setattr(application, "_spawn", fake_spawn)

    application.prepare()

    assert spawned == [("Ollama", ("/usr/bin/ollama", "serve"))]
    assert "Started local Ollama service" in capsys.readouterr().out


def test_start_builds_isolated_commands_and_shared_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeProcess] = []

    def fake_popen(command, **kwargs):
        process = FakeProcess(command, **kwargs)
        created.append(process)
        return process

    readiness_checks: list[tuple[str, str]] = []

    def ready(url, process, name, timeout):
        del process, timeout
        readiness_checks.append((url, name))

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(launcher, "_wait_for_http", ready)
    selected = settings(tmp_path)
    application = ApplicationLauncher(selected)

    application.start()

    assert len(created) == 2
    assert created[0].command[:4] == (
        launcher.sys.executable,
        "-m",
        "uvicorn",
        "ticket_support_ai.api:app",
    )
    assert created[1].command[:4] == (
        launcher.sys.executable,
        "-m",
        "streamlit",
        "run",
    )
    assert all(process.start_new_session for process in created)
    assert all(process.cwd == PROJECT_ROOT for process in created)
    assert created[0].env["TICKET_DATABASE_PATH"] == str(selected.database_path)
    assert created[1].env["TICKET_API_BASE_URL"] == selected.api_url
    assert str(PROJECT_ROOT / "src") in created[0].env["PYTHONPATH"]
    assert readiness_checks == [
        (f"{selected.api_url}/health", "FastAPI"),
        (selected.ui_url, "Streamlit"),
    ]


def test_stop_terminates_owned_process_groups_in_reverse_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = FakeProcess(("api",), cwd=PROJECT_ROOT, env={}, start_new_session=True)
    second = FakeProcess(("ui",), cwd=PROJECT_ROOT, env={}, start_new_session=True)
    application = ApplicationLauncher(settings(tmp_path))
    application.processes = [
        ManagedProcess("FastAPI", first),
        ManagedProcess("Streamlit", second),
    ]
    signals: list[tuple[int, int]] = []

    def capture(process, signal_number):
        signals.append((process.pid, signal_number))
        process.returncode = -signal_number

    monkeypatch.setattr(launcher, "_signal_process_group", capture)

    application.stop()
    application.stop()

    assert signals == [
        (second.pid, signal.SIGTERM),
        (first.pid, signal.SIGTERM),
    ]


def test_wait_reports_the_service_that_exited(tmp_path: Path) -> None:
    process = FakeProcess(("api",), cwd=PROJECT_ROOT, env={}, start_new_session=True)
    process.returncode = 7
    application = ApplicationLauncher(settings(tmp_path))
    application.processes = [ManagedProcess("FastAPI", process)]

    with pytest.raises(LauncherError, match="FastAPI exited.*code 7"):
        application.wait()


def test_main_rejects_conflicting_ports_before_startup(tmp_path: Path) -> None:
    result = launcher.main(
        [
            "--database",
            str(tmp_path / "tickets.db"),
            "--api-port",
            "9000",
            "--ui-port",
            "9000",
        ],
        project_root=PROJECT_ROOT,
    )

    assert result == 2
