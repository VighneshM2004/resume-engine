"""Probe endpoints with fake dependency checks: no network, runs in CI unit job."""

import threading
import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.readiness import Check, CheckResult


def ok(name: str) -> Check:
    return lambda: CheckResult(name, ok=True)  # type: ignore[arg-type]


def failing(name: str, code: str) -> Check:
    return lambda: CheckResult(name, ok=False, error_code=code)  # type: ignore[arg-type]


def client_with(checks: list[Check]) -> TestClient:
    return TestClient(create_app(checks=checks))


def test_health_is_ok_even_when_every_dependency_is_down() -> None:
    checks = [failing("database", "DATABASE_UNAVAILABLE"), failing("redis", "REDIS_UNAVAILABLE")]
    with client_with(checks) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_200_when_all_checks_pass() -> None:
    with client_with([ok("database"), ok("redis"), ok("storage")]) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert all(c["ok"] for c in body["checks"].values())


def test_ready_returns_503_and_names_the_failed_dependency() -> None:
    checks = [ok("database"), failing("redis", "REDIS_UNAVAILABLE"), ok("storage")]
    with client_with(checks) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["redis"] == {"ok": False, "error_code": "REDIS_UNAVAILABLE"}
    assert body["checks"]["database"]["ok"] is True


def test_ready_runs_checks_concurrently() -> None:
    # Three checks that each take 0.3 s must finish in well under 0.9 s.
    barrier = threading.Barrier(3, timeout=2)

    def slow(name: str) -> Check:
        def check() -> CheckResult:
            barrier.wait()  # deadlocks (then times out) if checks run one by one
            time.sleep(0.3)
            return CheckResult(name, ok=True)  # type: ignore[arg-type]

        return check

    with client_with([slow("database"), slow("redis"), slow("storage")]) as client:
        started = time.perf_counter()
        response = client.get("/ready")
        elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert elapsed < 0.8


def test_openapi_documents_both_probes() -> None:
    with client_with([]) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert "/health" in paths
    assert "/ready" in paths
