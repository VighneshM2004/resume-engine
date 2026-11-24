"""Liveness and readiness probes.

/health answers "is the process alive?" and never touches dependencies, so
an orchestrator doesn't restart a healthy API just because Postgres blipped.
/ready answers "can this instance serve traffic?" and checks every
dependency; a failing /ready takes the instance out of rotation instead.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from app.services.readiness import Check, CheckResult

router = APIRouter(tags=["probes"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class CheckStatus(BaseModel):
    ok: bool
    error_code: str | None = None


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckStatus]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
def ready(request: Request, response: Response) -> ReadyResponse:
    checks: list[Check] = request.app.state.readiness_checks
    results = _run_concurrently(checks)

    all_ok = all(r.ok for r in results)
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(
        status="ready" if all_ok else "not_ready",
        checks={r.name: CheckStatus(ok=r.ok, error_code=r.error_code) for r in results},
    )


def _run_concurrently(checks: list[Check]) -> list[CheckResult]:
    # Concurrent so the probe's worst case is one timeout, not the sum of all.
    if not checks:
        return []
    with ThreadPoolExecutor(max_workers=len(checks)) as pool:
        return list(pool.map(lambda check: check(), checks))
