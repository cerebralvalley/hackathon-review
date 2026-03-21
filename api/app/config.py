"""App settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path


class Settings:
    @property
    def database_url(self) -> str:
        return os.environ.get("DATABASE_URL", "sqlite:///./hackathon_review.db")

    @property
    def data_root(self) -> Path:
        """Root directory for all hackathon run data (CSVs, outputs)."""
        return Path(os.environ.get("DATA_ROOT", "./data")).resolve()

    @property
    def cors_origins(self) -> list[str]:
        raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
        return [o.strip() for o in raw.split(",")]


settings = Settings()
