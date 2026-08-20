"""Production configuration must fail loudly rather than fall back to a default.

A published default secret is worse than a crash: the application keeps
serving, and every token it issues can be forged by anyone who has read this
repository.
"""

import pytest

from config import ConfigError, Settings


def _settings(monkeypatch, **env):
    for key in ("ENVIRONMENT", "JWT_SECRET", "ADMIN_PASSWORD", "ADMIN_EMAIL",
                "CORS_ORIGINS", "COOKIE_SECURE", "COOKIE_SAMESITE", "MONGO_URL", "DB_NAME"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MONGO_URL", "mongodb://mongodb:27017")
    monkeypatch.setenv("DB_NAME", "fleet_manager")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings()


GOOD_SECRET = "b7f4d2a19c3e5f60a8d1b4c7e9f2a5d8c1b4e7f0a3d6c9b2e5f8a1d4c7b0e3f6"
GOOD_PASSWORD = "spravne-dlouhe-heslo-2026"


def test_production_refuses_to_start_without_a_jwt_secret(monkeypatch):
    settings = _settings(monkeypatch, ENVIRONMENT="production", ADMIN_PASSWORD=GOOD_PASSWORD)

    with pytest.raises(ConfigError, match="JWT_SECRET"):
        settings.validate()


def test_production_refuses_the_published_default_secret(monkeypatch):
    settings = _settings(
        monkeypatch,
        ENVIRONMENT="production",
        JWT_SECRET="changeme-use-random-64-chars",
        ADMIN_PASSWORD=GOOD_PASSWORD,
    )

    problems = settings.problems()
    assert any("JWT_SECRET" in p for p in problems)
    with pytest.raises(ConfigError):
        settings.validate()


def test_production_refuses_a_short_secret(monkeypatch):
    settings = _settings(monkeypatch, ENVIRONMENT="production",
                         JWT_SECRET="kratky", ADMIN_PASSWORD=GOOD_PASSWORD)

    assert any("krátký" in p for p in settings.problems())


def test_production_refuses_the_documented_admin_password(monkeypatch):
    settings = _settings(monkeypatch, ENVIRONMENT="production",
                         JWT_SECRET=GOOD_SECRET, ADMIN_PASSWORD="Admin123!")

    assert any("ADMIN_PASSWORD" in p for p in settings.problems())


def test_production_refuses_a_missing_admin_password(monkeypatch):
    settings = _settings(monkeypatch, ENVIRONMENT="production", JWT_SECRET=GOOD_SECRET)

    assert any("ADMIN_PASSWORD" in p for p in settings.problems())


def test_wildcard_cors_with_cookies_is_refused_in_production(monkeypatch):
    """`*` plus credentials would let any site act as a logged-in user."""
    settings = _settings(monkeypatch, ENVIRONMENT="production", JWT_SECRET=GOOD_SECRET,
                         ADMIN_PASSWORD=GOOD_PASSWORD, CORS_ORIGINS="*")

    assert any("CORS_ORIGINS" in p for p in settings.problems())


def test_samesite_none_requires_secure(monkeypatch):
    """A SameSite=None cookie without Secure is dropped by every browser."""
    settings = _settings(monkeypatch, ENVIRONMENT="production", JWT_SECRET=GOOD_SECRET,
                         ADMIN_PASSWORD=GOOD_PASSWORD,
                         COOKIE_SAMESITE="none", COOKIE_SECURE="false")

    assert any("COOKIE_SECURE" in p for p in settings.problems())


def test_a_correct_production_configuration_validates(monkeypatch):
    settings = _settings(monkeypatch, ENVIRONMENT="production", JWT_SECRET=GOOD_SECRET,
                         ADMIN_PASSWORD=GOOD_PASSWORD)

    settings.validate()  # must not raise
    assert settings.is_production is True
    assert settings.cookie_secure is False      # same-origin HTTP deployment
    assert settings.cookie_samesite == "lax"
    assert settings.cors_origins == []          # no CORS middleware at all
    assert settings.allow_mock_data is False    # demo generators off


def test_development_is_permissive_but_still_needs_a_secret(monkeypatch):
    settings = _settings(monkeypatch, ENVIRONMENT="development", JWT_SECRET="dev-only-secret")

    settings.validate()  # short secret tolerated outside production
    assert settings.is_production is False
    assert settings.allow_mock_data is True


def test_summary_never_leaks_a_secret(monkeypatch):
    settings = _settings(monkeypatch, ENVIRONMENT="production", JWT_SECRET=GOOD_SECRET,
                         ADMIN_PASSWORD=GOOD_PASSWORD,
                         MONGO_URL="mongodb://user:hunter2@db.internal:27017/fleet")

    summary = repr(settings.safe_summary())

    assert GOOD_SECRET not in summary
    assert GOOD_PASSWORD not in summary
    assert "hunter2" not in summary
    assert "db.internal:27017" in summary
    assert summary.count("jwt_secret_configured': True") == 1


def test_no_real_secret_is_committed_to_the_repository():
    """The template must ship empty values, not working credentials."""
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / ".env.example"
    assert example.exists()
    text = example.read_text()
    for line in text.splitlines():
        if line.startswith(("JWT_SECRET=", "ADMIN_PASSWORD=", "RESEND_API_KEY=")):
            assert line.split("=", 1)[1].strip() == "", f"{line} musí být prázdné"
