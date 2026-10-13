"""Pipeline configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, validator


class Settings(BaseModel):
    """Pipeline settings loaded from .env or environment variables."""

    environment: str = Field(default="development", description="development or production")
    database_url: str | None = Field(
        default=None, 
        description="PostgreSQL connection string. If not provided, constructed from "
                    "individual POSTGRES_* env vars."
    )
    anthropic_api_key: str | None = Field(default=None, description="Optional: for LLM generation outside pSEO")
    dataforseo_login: str | None = Field(default=None, description="Optional: DataForSEO credentials")
    dataforseo_password: str | None = Field(default=None, description="Optional: DataForSEO credentials")
    serpapi_api_key: str | None = Field(default=None, description="Optional: SerpAPI key")
    keywords_everywhere_api_key: str | None = Field(default=None, description="Optional: Keywords Everywhere key")
    moz_access_id: str | None = Field(default=None, description="Optional: Moz access ID")
    moz_secret_key: str | None = Field(default=None, description="Optional: Moz secret key")

    @validator("environment")
    def validate_environment(cls, v):
        if v not in ("development", "production"):
            raise ValueError("environment must be 'development' or 'production'")
        return v

    @validator("database_url", pre=True)
    def assemble_db_url(cls, v: str | None = None) -> str:
        """Build DATABASE_URL from individual env vars if not provided."""
        if v:
            return v
        # Build from individual env vars
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        dbname = os.getenv("POSTGRES_DB", "seo_aeo_geo")
        user = os.getenv("POSTGRES_USER", "postgres")
        password = os.getenv("POSTGRES_PASSWORD", "")
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"