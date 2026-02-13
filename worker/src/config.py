from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerConfig(BaseSettings):
    server_url: str = "http://localhost:8000"
    redis_url: str = "redis://localhost:6379"
    worker_name: str | None = None
    executor_type: str = "claude-code"
    heartbeat_interval: int = 30
    duration: int | None = None  # None=infinite, seconds
    registration_token: str | None = None

    model_config = SettingsConfigDict(env_prefix="BSNEXUS_", env_file=".env")
