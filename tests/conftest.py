"""Test configuration and fixtures for M1.

Unit tests use NO PostgreSQL (in-memory/python fixtures).
Database integration tests use Docker-based PostgreSQL and are marked with @pytest.mark.integration.
"""

import json
import os
import pytest
from typing import Any, Dict, List, Optional

# ---- Markers ----
# Integration tests require Docker PostgreSQL
# Unit tests run without any DB

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "integration: Mark test as needing Docker PostgreSQL")
    config.addinivalue_line("markers", "unit: Mark test as unit test (no DB required)")