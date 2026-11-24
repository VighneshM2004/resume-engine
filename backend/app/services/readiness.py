"""Dependency checks behind GET /ready.

Each check answers one question: "can this process use dependency X right
now?" A check never raises: it returns a CheckResult. Failure details stay
in the server log; clients only see the dependency name and a fixed code,
so a probe can't leak hostnames, credentials or stack traces.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import boto3
import psycopg
import redis
from botocore.config import Config as BotoConfig
from mypy_boto3_s3 import S3Client

from app.core.config import Settings

logger = logging.getLogger(__name__)

CheckName = Literal["database", "redis", "storage"]


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: CheckName
    ok: bool
    # Stable, client-safe code. None when ok.
    error_code: str | None = None


Check = Callable[[], CheckResult]


def make_s3_client(settings: Settings) -> S3Client:
    timeout = settings.ready_check_timeout_seconds
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        config=BotoConfig(
            connect_timeout=timeout,
            read_timeout=timeout,
            retries={"max_attempts": 1},
            # SeaweedFS (like most self-hosted S3) needs path-style URLs.
            s3={"addressing_style": "path"},
        ),
    )


def check_database(settings: Settings) -> CheckResult:
    try:
        with psycopg.connect(
            settings.database_url.get_secret_value(),
            connect_timeout=max(1, int(settings.ready_check_timeout_seconds)),
        ) as conn:
            conn.execute("SELECT 1")
    except Exception:
        logger.warning("readiness: database check failed", exc_info=True)
        return CheckResult("database", ok=False, error_code="DATABASE_UNAVAILABLE")
    return CheckResult("database", ok=True)


def check_redis(settings: Settings) -> CheckResult:
    timeout = settings.ready_check_timeout_seconds
    client: redis.Redis = redis.Redis.from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
    )
    try:
        client.ping()
    except Exception:
        logger.warning("readiness: redis check failed", exc_info=True)
        return CheckResult("redis", ok=False, error_code="REDIS_UNAVAILABLE")
    finally:
        client.close()
    return CheckResult("redis", ok=True)


def check_storage(settings: Settings, client: S3Client) -> CheckResult:
    try:
        # head_bucket proves reachability, valid credentials and that the
        # bucket exists, in one cheap call that reads no object data.
        client.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        logger.warning("readiness: storage check failed", exc_info=True)
        return CheckResult("storage", ok=False, error_code="STORAGE_UNAVAILABLE")
    return CheckResult("storage", ok=True)


def ensure_bucket(settings: Settings, client: S3Client) -> None:
    """Create the bucket if missing. Called at startup in dev/test only."""
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", []) if "Name" in b}
    if settings.s3_bucket not in existing:
        client.create_bucket(Bucket=settings.s3_bucket)
        logger.info("created bucket %s", settings.s3_bucket)


def default_checks(settings: Settings, s3_client: S3Client) -> list[Check]:
    return [
        lambda: check_database(settings),
        lambda: check_redis(settings),
        lambda: check_storage(settings, s3_client),
    ]
