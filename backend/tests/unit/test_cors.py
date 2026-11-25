"""CORS: only listed browser origins may call the API."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import CorsSettings
from app.main import create_app

ALLOWED = "http://localhost:8080"
OTHER = "https://evil.example"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(checks=[], cors_origins=[ALLOWED]))


def test_allowed_origin_gets_cors_header(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": ALLOWED})
    assert response.headers.get("access-control-allow-origin") == ALLOWED


def test_other_origin_gets_no_cors_header(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": OTHER})
    assert "access-control-allow-origin" not in response.headers


def test_preflight_from_allowed_origin_succeeds(client: TestClient) -> None:
    response = client.options(
        "/ready",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ALLOWED


def test_preflight_from_other_origin_is_rejected(client: TestClient) -> None:
    response = client.options(
        "/ready",
        headers={"Origin": OTHER, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_wildcard_origin_is_refused_by_settings() -> None:
    with pytest.raises(ValidationError):
        CorsSettings(cors_allowed_origins=["*"])
