"""Opt-in HTTP test through FastAPI and the installed local Qwen model."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import pytest

from ticket_support_ai.api import create_app
from ticket_support_ai.database import ingest_csv_snapshot

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_OLLAMA") != "1",
        reason="set RUN_LIVE_OLLAMA=1 to call the local Ollama service",
    ),
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = PROJECT_ROOT / "support_tickets.csv"


def test_live_health_and_query_endpoints(tmp_path: Path) -> None:
    database = tmp_path / "tickets.db"
    ingest_csv_snapshot(SOURCE_CSV, database)
    app = create_app(database)

    async def exercise() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            health = await client.get("/health")
            query = await client.post(
                "/query",
                json={"question": "How many tickets are currently open?"},
            )
            return health, query

    health, query = asyncio.run(exercise())

    assert health.status_code == 200
    assert health.json()["status"] == "ready"
    assert query.status_code == 200
    assert query.json()["data"]["value"] == 111
