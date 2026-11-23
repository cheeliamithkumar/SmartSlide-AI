"""Application configuration loaded from environment variables / .env file."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SmartSlide AI"
    environment: Literal["development", "production", "test"] = "development"

    # --- AI provider -------------------------------------------------------
    ai_provider: Literal["mock", "claude", "gemini"] = "mock"
    anthropic_api_key: str | None = None
    claude_model: str = "claude-sonnet-5-5"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    ai_timeout_seconds: float = 90.0
    ai_max_retries: int = 3
    # When the configured provider fails, fall back to the offline heuristic engine.
    ai_fallback_to_mock: bool = True

    # --- Storage -----------------------------------------------------------
    storage_dir: Path = BACKEND_DIR / "storage"
    database_url: str = ""
    # Vercel's Neon/Postgres integration exposes POSTGRES_URL; used when DATABASE_URL is empty.
    postgres_url: str = ""
    # Vercel Blob (enables direct browser uploads larger than the 4.5 MB function limit)
    blob_read_write_token: str = ""

    # --- Execution mode ------------------------------------------------------
    # Serverless platforms (e.g. Vercel) have no persistent disk or background threads:
    # jobs then run inside the request and extracted text is stored in the database.
    serverless: bool = Field(default_factory=lambda: bool(os.environ.get("VERCEL")))
    jobs_sync: bool | None = None

    # --- Limits ------------------------------------------------------------
    max_upload_mb: int = 25
    max_pages: int = 300
    chunk_max_chars: int = 12000
    ocr_enabled: bool = True
    ocr_language: str = "eng"
    ocr_max_pages: int = 60

    # --- Cleanup -----------------------------------------------------------
    file_retention_hours: float = 24.0
    cleanup_interval_minutes: float = 30.0

    # --- HTTP --------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Deck defaults -----------------------------------------------------
    summary_slides_default: int = 12
    detailed_slides_default: int = 24

    @field_validator("storage_dir", mode="before")
    @classmethod
    def _resolve_storage(cls, v: str | Path) -> Path:
        p = Path(v)
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    def model_post_init(self, __context) -> None:
        if self.serverless and not os.environ.get("STORAGE_DIR"):
            # only /tmp is writable on serverless platforms
            self.storage_dir = Path("/tmp/smartslide")

    @property
    def run_jobs_inline(self) -> bool:
        return self.serverless if self.jobs_sync is None else self.jobs_sync

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.storage_dir / "outputs"

    @property
    def extracted_dir(self) -> Path:
        return self.storage_dir / "extracted"

    @property
    def resolved_database_url(self) -> str:
        url = self.database_url or self.postgres_url
        if not url:
            return f"sqlite:///{self.storage_dir / 'smartslide.db'}"
        # normalise Heroku/Neon style URLs for SQLAlchemy + psycopg 3
        url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)
        return url

    @property
    def persistent_database(self) -> bool:
        return not self.resolved_database_url.startswith("sqlite") or not self.serverless

    def ensure_dirs(self) -> None:
        for d in (self.storage_dir, self.uploads_dir, self.outputs_dir, self.extracted_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
