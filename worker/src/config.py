from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerConfig(BaseSettings):
    server_url: str = "http://localhost:8000"
    worker_name: str | None = None
    executor_type: str = "claude-code"
    heartbeat_interval: int = 30
    poll_interval: int = 2  # seconds between empty poll retries
    poll_timeout: int = 10  # HTTP timeout for poll (server blocks ~5s)
    duration: int | None = None  # None=infinite, seconds
    registration_token: str | None = None

    # Saved after register (like gitlab-runner config.toml)
    worker_id: str | None = None
    worker_token: str | None = None

    model_config = SettingsConfigDict(env_prefix="BSNEXUS_", env_file=".env", extra="ignore")

    @field_validator("duration", "heartbeat_interval", "poll_interval", "poll_timeout", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v
