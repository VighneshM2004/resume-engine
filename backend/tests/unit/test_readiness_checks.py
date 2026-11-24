"""Real check functions against unreachable dependencies.

Port 1 on localhost is reserved and closed, so connections are refused
immediately: this proves each check reports failure (with a safe code)
instead of raising or hanging, without needing any service running.
"""

import time

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.readiness import (
    check_database,
    check_redis,
    check_storage,
    make_s3_client,
)

SECRET = "super-secret-password"


@pytest.fixture
def unreachable() -> Settings:
    return Settings(
        app_env="test",
        database_url=SecretStr(f"postgresql://u:{SECRET}@127.0.0.1:1/db"),
        redis_url=SecretStr("redis://127.0.0.1:1/0"),
        s3_endpoint_url="http://127.0.0.1:1",
        s3_access_key_id=SecretStr("k"),
        s3_secret_access_key=SecretStr(SECRET),
        s3_bucket="resumes",
        ready_check_timeout_seconds=1,
    )


def test_database_check_reports_failure(unreachable: Settings) -> None:
    result = check_database(unreachable)
    assert result.ok is False
    assert result.error_code == "DATABASE_UNAVAILABLE"


def test_redis_check_reports_failure(unreachable: Settings) -> None:
    result = check_redis(unreachable)
    assert result.ok is False
    assert result.error_code == "REDIS_UNAVAILABLE"


def test_storage_check_reports_failure_within_timeout(unreachable: Settings) -> None:
    started = time.perf_counter()
    result = check_storage(unreachable, make_s3_client(unreachable))
    assert result.ok is False
    assert result.error_code == "STORAGE_UNAVAILABLE"
    assert time.perf_counter() - started < 5


def test_failure_codes_never_contain_secrets(unreachable: Settings) -> None:
    results = [
        check_database(unreachable),
        check_redis(unreachable),
        check_storage(unreachable, make_s3_client(unreachable)),
    ]
    for result in results:
        assert SECRET not in repr(result)


def test_settings_repr_hides_secrets(unreachable: Settings) -> None:
    assert SECRET not in repr(unreachable)
