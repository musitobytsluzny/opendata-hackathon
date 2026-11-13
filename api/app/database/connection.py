from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Settings(BaseSettings):
    database_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"
    gemini_timeout_seconds: int = Field(default=60, ge=5, le=180)
    gemini_max_output_tokens: int = Field(default=2048, ge=256, le=8192)
    llm_max_concurrent: int = Field(default=4, ge=1, le=16)
    mcp_server_url: str = "http://mcp:8000/mcp/sse"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env", extra="ignore"
    )


settings = Settings()

engine = create_engine(
    make_url(settings.database_url).set(drivername="postgresql+psycopg"), pool_pre_ping=True
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
