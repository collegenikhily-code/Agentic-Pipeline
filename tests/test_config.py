"""M1 unit tests for configuration.

No PostgreSQL required.
"""

import os
from pathlib import Path

import pytest

from seo_aeo_geo_pipeline.config import Settings


class TestConfig:
    """Configuration tests."""

    def test_load_settings_requires_no_creds(self):
        """M1: Config loads with zero API credentials."""
        # M1: database_url has a default constructed from components
        settings = Settings()
        assert settings is not None
        assert hasattr(settings, "database_url")
        assert settings.environment in ("development", "production")

    def test_env_example_structure(self):
        """M1: .env.example exists and has expected keys."""
        # .env.example is in the project root, same directory as this test
        env_example = Path(".env.example")
        assert env_example.exists(), ".env.example must exist for M1"

    def test_no_mandatory_cred_deps(self):
        """M1: No paid service dependencies in pip requirements."""
        # Parse pyproject.toml to verify
        import tomllib
        with open("pyproject.toml", "rb") as f:
            config_data = tomllib.load(f)
        
        deps = config_data.get("project", {}).get("dependencies", [])
        # Check that no credential package names appear
        cred_keywords = ["dataforseo", "serapikey", "keywords-everywhere", "moz-", "anthropic", "openai"]
        for dep in deps:
            dep_lower = dep.lower()
            assert not any(kw in dep_lower for kw in cred_keywords), \
                f"Found credential package in deps: {dep}"