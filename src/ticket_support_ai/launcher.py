"""Single-command startup and process supervision for the local application."""

from __future__ import annotations

import argparse
import asyncio
import atexit
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from urllib.error import URLError
from urllib.request import urlopen

from ticket_support_ai.database import ingest_csv_snapshot
from ticket_support_ai.llm import LLMError, OllamaInterpreter, OllamaModelStatus

DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8000
DEFAULT_UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8501


class LauncherError(RuntimeError):
    """Safe startup or supervision failure shown to the operator."""


@dataclass(frozen=True, slots=True)
class LauncherSettings:
    """Validated paths, addresses, and startup policy for both services."""

    project_root: Path
    source_csv: Path
    database_path: Path
    api_host: str = DEFAULT_API_HOST
    api_port: int = DEFAULT_API_PORT
    ui_host: str = DEFAULT_UI_HOST
    ui_port: int = DEFAULT_UI_PORT
    startup_timeout_seconds: float = 45.0
    check_model: bool = True
    warm_model: bool = True

    def __post_init__(self) -> None:
        if not self.project_root.is_dir():
            raise ValueError(f"Project root does not exist: {self.project_root}")
        for name, port in (("API", self.api_port), ("UI", self.ui_port)):
            if not 1 <= port <= 65535:
                raise ValueError(f"{name} port must be between 1 and 65535.")
        if self.api_host == self.ui_host and self.api_port == self.ui_port:
            raise ValueError("API and UI must use different host/port combinations.")
        if self.startup_timeout_seconds <= 0:
            raise ValueError("Startup timeout must be greater than zero.")

    @property
    def api_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"

    @property
    def ui_url(self) -> str:
        return f"http://{self.ui_host}:{self.ui_port}"


@dataclass(slots=True)
class ManagedProcess:
    """One child process and its operator-facing service name."""

    name: str
    process: subprocess.Popen[bytes]


class ApplicationLauncher:
    """Prepare data, start both services, supervise them, and stop cleanly."""

    def __init__(self, settings: LauncherSettings) -> None:
        self.settings = settings
        self.processes: list[ManagedProcess] = []
        self._stopped = False

    def prepare(self) -> None:
        """Validate local prerequisites and atomically prepare the dataset."""

        _ensure_port_available(self.settings.api_host, self.settings.api_port, "API")
        _ensure_port_available(self.settings.ui_host, self.settings.ui_port, "UI")
        result = ingest_csv_snapshot(
            self.settings.source_csv,
            self.settings.database_path,
        )
        action = "reused" if result.reused_existing else "ingested"
        print(
            f"Dataset ready: {result.row_count} rows {action} at "
            f"{result.database_path}",
            flush=True,
        )
        if self.settings.check_model:
            interpreter = OllamaInterpreter()
            status = asyncio.run(interpreter.readiness())
            if not status.service_available:
                status = self._start_local_ollama(interpreter)
            if status.service_available and status.model_available:
                if self.settings.warm_model:
                    print("Warming Qwen before accepting questions...", flush=True)
                    try:
                        asyncio.run(interpreter.warmup())
                    except LLMError as exc:
                        print(f"Warning: model warm-up failed: {exc}", flush=True)
                print(
                    f"Model ready: {status.model} through Ollama "
                    f"{status.version or 'unknown version'}",
                    flush=True,
                )
            else:
                explanation = status.error or "local model is unavailable"
                setup = (
                    "Install Ollama from https://ollama.com/download, then run "
                    "`ollama pull qwen2.5:3b`."
                    if not status.service_available
                    else f"Run `ollama pull {status.model}`."
                )
                print(
                    f"Warning: {explanation} Natural-language queries will be "
                    "unavailable until Ollama and the configured model are ready. "
                    "The API, health check, and anomaly workflow can still start. "
                    f"Setup: {setup}",
                    flush=True,
                )

    def _start_local_ollama(
        self, interpreter: OllamaInterpreter
    ) -> OllamaModelStatus:
        """Start an installed local Ollama service and wait for its API."""

        executable = shutil.which("ollama")
        if executable is None:
            return asyncio.run(interpreter.readiness())
        print("Ollama is not reachable; starting `ollama serve`...", flush=True)
        managed = self._spawn("Ollama", (executable, "serve"), os.environ.copy())
        deadline = time.monotonic() + self.settings.startup_timeout_seconds
        status = asyncio.run(interpreter.readiness())
        while not status.service_available and time.monotonic() < deadline:
            if managed.process.poll() is not None:
                break
            time.sleep(0.25)
            status = asyncio.run(interpreter.readiness())
        if status.service_available:
            print("Started local Ollama service.", flush=True)
        return status

    def start(self) -> None:
        """Start FastAPI first, then Streamlit after the API responds."""

        child_environment = os.environ.copy()
        source_path = str(self.settings.project_root / "src")
        existing_pythonpath = child_environment.get("PYTHONPATH")
        child_environment["PYTHONPATH"] = (
            source_path
            if not existing_pythonpath
            else os.pathsep.join((source_path, existing_pythonpath))
        )
        child_environment["TICKET_API_BASE_URL"] = self.settings.api_url
        child_environment["TICKET_DATABASE_PATH"] = str(self.settings.database_path)

        api_command = (
            sys.executable,
            "-m",
            "uvicorn",
            "ticket_support_ai.api:app",
            "--app-dir",
            "src",
            "--host",
            self.settings.api_host,
            "--port",
            str(self.settings.api_port),
        )
        api = self._spawn("FastAPI", api_command, child_environment)
        _wait_for_http(
            f"{self.settings.api_url}/health",
            api.process,
            "FastAPI",
            self.settings.startup_timeout_seconds,
        )

        ui_command = (
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "src/ticket_support_ai/ui.py",
            "--server.address",
            self.settings.ui_host,
            "--server.port",
            str(self.settings.ui_port),
            "--server.headless",
            "true",
            "--server.fileWatcherType",
            "none",
            "--browser.gatherUsageStats",
            "false",
        )
        ui = self._spawn("Streamlit", ui_command, child_environment)
        _wait_for_http(
            self.settings.ui_url,
            ui.process,
            "Streamlit",
            self.settings.startup_timeout_seconds,
        )
        print(f"Application ready: {self.settings.ui_url}", flush=True)
        print(f"API documentation: {self.settings.api_url}/docs", flush=True)
        print("Press Ctrl+C to stop both services.", flush=True)

    def wait(self) -> None:
        """Block until interrupted or until either service exits unexpectedly."""

        while True:
            for managed in self.processes:
                exit_code = managed.process.poll()
                if exit_code is not None:
                    raise LauncherError(
                        f"{managed.name} exited unexpectedly with code {exit_code}."
                    )
            time.sleep(0.5)

    def stop(self) -> None:
        """Terminate every owned process group, escalating only when necessary."""

        if self._stopped:
            return
        self._stopped = True
        running = [
            item for item in reversed(self.processes) if item.process.poll() is None
        ]
        for managed in running:
            _signal_process_group(managed.process, signal.SIGTERM)
        deadline = time.monotonic() + 8.0
        for managed in running:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                managed.process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                _signal_process_group(managed.process, signal.SIGKILL)
                managed.process.wait(timeout=2.0)
        if running:
            print("Stopped launcher-owned services.", flush=True)

    def run(self) -> int:
        """Execute the complete launcher lifecycle and return a shell status."""

        previous_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
        atexit.register(self.stop)
        try:
            self.prepare()
            self.start()
            self.wait()
        except KeyboardInterrupt:
            print("\nShutdown requested.", flush=True)
        except LauncherError as exc:
            print(f"Startup failed: {exc}", file=sys.stderr, flush=True)
            return 1
        except (OSError, ValueError) as exc:
            print(f"Preflight failed: {exc}", file=sys.stderr, flush=True)
            return 1
        finally:
            self.stop()
            atexit.unregister(self.stop)
            signal.signal(signal.SIGTERM, previous_sigterm)
        return 0

    def _spawn(
        self,
        name: str,
        command: Sequence[str],
        environment: dict[str, str],
    ) -> ManagedProcess:
        try:
            process = subprocess.Popen(
                command,
                cwd=self.settings.project_root,
                env=environment,
                start_new_session=True,
            )
        except OSError as exc:
            raise LauncherError(f"Could not start {name}: {exc}") from exc
        managed = ManagedProcess(name=name, process=process)
        self.processes.append(managed)
        return managed


def build_parser(project_root: Path) -> argparse.ArgumentParser:
    """Build the evaluator-facing command-line contract."""

    parser = argparse.ArgumentParser(
        description="Start the AI customer-ticket FastAPI and Streamlit services.",
    )
    parser.add_argument(
        "--source-csv",
        type=Path,
        default=project_root / "support_tickets.csv",
        help="Ticket CSV to validate and ingest before startup.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=project_root / "data/runtime/support_tickets.db",
        help="Generated SQLite snapshot path.",
    )
    parser.add_argument("--api-host", default=DEFAULT_API_HOST)
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--ui-host", default=DEFAULT_UI_HOST)
    parser.add_argument("--ui-port", type=int, default=DEFAULT_UI_PORT)
    parser.add_argument("--startup-timeout", type=float, default=45.0)
    parser.add_argument(
        "--skip-model-warmup", action="store_true",
        help="Skip the bounded startup inference that preloads Qwen.",
    )
    parser.add_argument(
        "--skip-model-check",
        action="store_true",
        help="Start without the optional Ollama readiness preflight.",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, project_root: Path | None = None) -> int:
    """Parse settings and run the supervised local application."""

    root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    arguments = build_parser(root).parse_args(argv)
    try:
        settings = LauncherSettings(
            project_root=root,
            source_csv=arguments.source_csv.expanduser().resolve(),
            database_path=arguments.database.expanduser().resolve(),
            api_host=arguments.api_host,
            api_port=arguments.api_port,
            ui_host=arguments.ui_host,
            ui_port=arguments.ui_port,
            startup_timeout_seconds=arguments.startup_timeout,
            check_model=not arguments.skip_model_check,
            warm_model=not arguments.skip_model_warmup,
        )
    except ValueError as exc:
        print(f"Invalid launcher configuration: {exc}", file=sys.stderr)
        return 2
    return ApplicationLauncher(settings).run()


def _ensure_port_available(host: str, port: int, service_name: str) -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            candidate.bind((host, port))
    except OSError as exc:
        raise LauncherError(
            f"{service_name} address {host}:{port} is unavailable: {exc}. "
            "Stop the conflicting service or select another port."
        ) from exc


def _wait_for_http(
    url: str,
    process: subprocess.Popen[bytes],
    service_name: str,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response"
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise LauncherError(
                f"{service_name} exited during startup with code {exit_code}."
            )
        try:
            with urlopen(url, timeout=2.0) as response:
                if 200 <= response.status < 500:
                    return
                last_error = f"HTTP {response.status}"
        except (URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise LauncherError(
        f"{service_name} did not become ready within {timeout_seconds:g} seconds "
        f"({last_error})."
    )


def _signal_process_group(process: subprocess.Popen[bytes], signal_number: int) -> None:
    try:
        os.killpg(process.pid, signal_number)
    except (ProcessLookupError, PermissionError):
        if process.poll() is None:
            if signal_number == signal.SIGKILL:
                process.kill()
            else:
                process.terminate()


def _raise_keyboard_interrupt(signum: int, frame: FrameType | None) -> None:
    del signum, frame
    raise KeyboardInterrupt
