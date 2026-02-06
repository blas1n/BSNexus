from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Infrastructure
    redis_url: str = "redis://localhost:6379"
    database_url: str = "postgresql+asyncpg://bsnexus:bsnexus_dev@localhost:5432/bsnexus"

    # Security
    prompt_signing_key: str

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    debug: bool = False

    # LLM Defaults (fallback only - used when not specified at runtime)
    default_llm_model: Optional[str] = None
    default_llm_base_url: Optional[str] = None

    class Config:
        env_file = ".env"


settings = Settings()
