"""Fixtures for the live-server integration suite.

These tests talk to a running Fleet Manager over HTTP. They are excluded from
the default `pytest` run (see pytest.ini `testpaths`) and skipped entirely
unless a base URL is supplied:

    FLEET_BASE_URL=http://localhost \\
    FLEET_ADMIN_EMAIL=admin@example.com \\
    FLEET_ADMIN_PASSWORD=... \\
    pytest tests/integration

The base URL used to be a hard-coded preview hostname, which meant the suite
silently tested somebody else's deployment — or nothing at all.
"""

import os

import pytest

BASE_URL = (os.environ.get("FLEET_BASE_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
ADMIN_EMAIL = os.environ.get("FLEET_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("FLEET_ADMIN_PASSWORD", "")


def pytest_collection_modifyitems(config, items):
    for item in items:
        item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session", autouse=True)
def require_base_url():
    if not BASE_URL:
        pytest.skip("FLEET_BASE_URL není nastaven — integrační testy přeskočeny", allow_module_level=True)
    return BASE_URL


@pytest.fixture(scope="session")
def admin_credentials():
    if not (ADMIN_EMAIL and ADMIN_PASSWORD):
        pytest.skip("FLEET_ADMIN_EMAIL/FLEET_ADMIN_PASSWORD nejsou nastaveny")
    return {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
