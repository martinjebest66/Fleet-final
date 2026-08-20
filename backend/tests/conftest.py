"""Shared test fixtures.

The unit suite runs against an in-memory MongoDB (mongomock-motor) so it needs
neither a database server nor a deployed application. The live-server
integration scripts under `tests/integration/` are marked separately and are
skipped unless a base URL is provided.
"""

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Configure before importing the application: `config` reads the environment at
# import time, and the production checks would otherwise refuse these values.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-production-0123456789")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "fleet_manager_test")


@pytest.fixture
def mock_db():
    """A fresh in-memory database for one test."""
    from mongomock_motor import AsyncMongoMockClient

    return AsyncMongoMockClient()["fleet_test"]


@pytest.fixture
def anyio_backend():
    return "asyncio"
