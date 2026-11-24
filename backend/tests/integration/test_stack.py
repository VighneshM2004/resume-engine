"""Probes against the running compose stack (`make up` first).

Run with: make test-integration
Talks to the API over HTTP exactly as an orchestrator would.
"""

import os

import httpx
import pytest

pytestmark = pytest.mark.integration

API_URL = os.environ.get("API_URL", "http://localhost:8000")


def test_health_is_ok() -> None:
    response = httpx.get(f"{API_URL}/health", timeout=5)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_every_dependency_up() -> None:
    response = httpx.get(f"{API_URL}/ready", timeout=10)
    body = response.json()
    assert response.status_code == 200, body
    assert body["status"] == "ready"
    assert set(body["checks"]) == {"database", "redis", "storage"}
