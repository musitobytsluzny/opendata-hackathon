from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = Field(default=True, validation_alias="MCP_DEBUG")

    # Central API configuration
    CENTRAL_API_BASE_URL: str = "https://api.example.com/v1"
    CENTRAL_API_KEY: str = ""
    CENTRAL_API_TIMEOUT: float = 30.0

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
