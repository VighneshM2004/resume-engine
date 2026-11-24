"""Application settings, read from environment variables (and .env in dev).

Every setting has a matching line in .env.example. Secrets are typed as
SecretStr so they never appear in logs, reprs or error messages.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "staging"] = "dev"

    database_url: SecretStr
    redis_url: SecretStr

    s3_endpoint_url: str
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr
    s3_secret_access_key: SecretStr
    s3_bucket: str
    s3_auto_create_bucket: bool = False

    # Bounded so a misconfiguration can't make the probe hang for minutes.
    ready_check_timeout_seconds: float = Field(default=2.0, gt=0, le=10)


@lru_cache
def get_settings() -> Settings:
    # pydantic-settings fills required fields from the environment; mypy
    # can't see that, hence the ignore.
    return Settings()  # type: ignore[call-arg]
