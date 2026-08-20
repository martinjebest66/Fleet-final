"""Central runtime configuration for Fleet Manager.

Every environment-driven setting is resolved here exactly once so the rest of the
codebase never has to guess a default. In production the application refuses to
start with an unsafe configuration (missing/weak JWT secret, well-known admin
password) instead of silently falling back to a value that is public knowledge.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

logger = logging.getLogger("fleet.config")

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# Values that have been published in this repository / documentation and must
# therefore never be accepted as a real secret in a production deployment.
KNOWN_INSECURE_SECRETS = {
    "changeme",
    "changeme-use-random-64-chars",
    "change-me",
    "secret",
    "dev",
    "development",
    "fleet-manager-secret",
    "test",
    "dev-secret",
}

KNOWN_INSECURE_PASSWORDS = {
    "admin123!",
    "admin123",
    "admin",
    "password",
    "changeme",
    "heslo123",
}

MIN_JWT_SECRET_LENGTH = 32


def _redact_mongo_url(url: Optional[str]) -> Optional[str]:
    """Return host:port from a Mongo URL, dropping any embedded credentials."""
    if not url:
        return None
    without_scheme = url.split("://", 1)[-1]
    host_part = without_scheme.split("@")[-1].split("/")[0].split("?")[0]
    return host_part or None


class ConfigError(RuntimeError):
    """Raised when the process is started with an unusable configuration."""


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name, default)
    if isinstance(value, str):
        value = value.strip()
    return value or default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        logger.warning("Invalid integer for %s=%r, using default %s", name, raw, default)
        return default


class Settings:
    """Resolved application settings.

    Instantiating never raises; call :meth:`validate` to enforce the production
    rules so the caller decides when to fail (startup) versus when to tolerate
    a partial configuration (unit tests, tooling).
    """

    def __init__(self) -> None:
        self.environment: str = (_env("ENVIRONMENT") or _env("APP_ENV") or "production").lower()

        # --- database ---
        self.mongo_url: str = _env("MONGO_URL", "mongodb://localhost:27017")
        self.db_name: str = _env("DB_NAME", "fleet_manager")
        self.mongo_connect_timeout_ms: int = _env_int("MONGO_CONNECT_TIMEOUT_MS", 5000)
        self.mongo_startup_retries: int = _env_int("MONGO_STARTUP_RETRIES", 30)
        self.mongo_startup_retry_delay: float = float(_env_int("MONGO_STARTUP_RETRY_DELAY_SEC", 2))

        # --- auth ---
        self.jwt_secret: Optional[str] = _env("JWT_SECRET")
        self.jwt_algorithm: str = "HS256"
        self.access_token_hours: int = _env_int("ACCESS_TOKEN_HOURS", 12)
        self.refresh_token_days: int = _env_int("REFRESH_TOKEN_DAYS", 7)
        self.session_days: int = _env_int("SESSION_DAYS", 7)

        self.admin_email: str = (_env("ADMIN_EMAIL", "admin@autoskola.cz") or "").lower()
        self.admin_password: Optional[str] = os.environ.get("ADMIN_PASSWORD") or None
        # When false the seeded admin password is never overwritten on restart,
        # so a password changed by an operator survives a redeploy.
        self.admin_password_reset_on_start: bool = _env_bool("ADMIN_PASSWORD_RESET_ON_START", False)

        # --- cookies ---
        # Defaults target the supported deployment: browser -> Nginx -> FastAPI on
        # one origin. SameSite=Lax + Secure=false works on plain HTTP; operators
        # terminating TLS set COOKIE_SECURE=true (and SameSite=None only when the
        # frontend really is served from a different site).
        self.cookie_secure: bool = _env_bool("COOKIE_SECURE", False)
        self.cookie_samesite: str = (_env("COOKIE_SAMESITE", "lax") or "lax").lower()
        self.cookie_domain: Optional[str] = _env("COOKIE_DOMAIN")

        # --- CORS ---
        raw_origins = _env("CORS_ORIGINS", "")
        self.cors_origins: List[str] = [o.strip() for o in (raw_origins or "").split(",") if o.strip()]

        # --- Teltonika ---
        self.teltonika_enabled: bool = _env_bool("TELTONIKA_ENABLED", True)
        self.teltonika_host: str = _env("TELTONIKA_TCP_HOST", "0.0.0.0")
        self.teltonika_port: int = _env_int("TELTONIKA_TCP_PORT", 5027)
        self.teltonika_idle_timeout: int = _env_int("TELTONIKA_IDLE_TIMEOUT_SEC", 900)

        # --- uploads ---
        self.max_upload_bytes: int = _env_int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
        self.max_import_bytes: int = _env_int("MAX_IMPORT_BYTES", 25 * 1024 * 1024)

        # --- integrations ---
        self.resend_api_key: Optional[str] = _env("RESEND_API_KEY")
        self.sender_email: str = _env("SENDER_EMAIL", "onboarding@resend.dev")
        self.emergent_auth_url: str = _env(
            "EMERGENT_AUTH_URL",
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
        )

        # --- feature flags ---
        # Mock/simulated GPS generators write into the same collections as real
        # tracker data, so they stay off unless explicitly enabled.
        self.allow_mock_data: bool = _env_bool("ALLOW_MOCK_DATA", not self.is_production)
        self.ics_auto_sync_enabled: bool = _env_bool("ICS_AUTO_SYNC", True)
        self.ics_allow_private_hosts: bool = _env_bool("ICS_ALLOW_PRIVATE_HOSTS", False)

        # --- rate limiting ---
        self.login_rate_limit_attempts: int = _env_int("LOGIN_RATE_LIMIT_ATTEMPTS", 10)
        self.login_rate_limit_window_sec: int = _env_int("LOGIN_RATE_LIMIT_WINDOW_SEC", 300)

    @property
    def is_production(self) -> bool:
        return self.environment not in ("dev", "development", "test", "testing", "local")

    def problems(self) -> List[str]:
        """Return a list of fatal configuration problems (empty when usable)."""
        issues: List[str] = []

        if not self.mongo_url:
            issues.append("MONGO_URL není nastaven.")
        if not self.db_name:
            issues.append("DB_NAME není nastaven.")

        if not self.jwt_secret:
            issues.append(
                "JWT_SECRET není nastaven. Vygenerujte náhodný secret, např. "
                "`openssl rand -hex 32`, a předejte ho přes prostředí."
            )
        elif self.is_production:
            if self.jwt_secret.lower() in KNOWN_INSECURE_SECRETS:
                issues.append("JWT_SECRET je veřejně známá výchozí hodnota — nastavte vlastní náhodný secret.")
            elif len(self.jwt_secret) < MIN_JWT_SECRET_LENGTH:
                issues.append(
                    f"JWT_SECRET je příliš krátký ({len(self.jwt_secret)} znaků, "
                    f"minimum {MIN_JWT_SECRET_LENGTH})."
                )

        if self.is_production:
            if not self.admin_password:
                issues.append(
                    "ADMIN_PASSWORD není nastaven. Bez něj nelze bezpečně založit administrátorský účet."
                )
            elif self.admin_password.lower() in KNOWN_INSECURE_PASSWORDS:
                issues.append("ADMIN_PASSWORD je veřejně známé výchozí heslo — zvolte vlastní.")
            elif len(self.admin_password) < 10:
                issues.append("ADMIN_PASSWORD musí mít alespoň 10 znaků.")

            if "*" in self.cors_origins:
                issues.append(
                    "CORS_ORIGINS=* nelze kombinovat s cookie autentizací v produkci. "
                    "Uveďte konkrétní originy, nebo pole nechte prázdné (same-origin nasazení)."
                )

        if self.cookie_samesite not in ("lax", "strict", "none"):
            issues.append(f"COOKIE_SAMESITE má neplatnou hodnotu {self.cookie_samesite!r}.")
        elif self.cookie_samesite == "none" and not self.cookie_secure:
            issues.append(
                "COOKIE_SAMESITE=none vyžaduje COOKIE_SECURE=true, jinak prohlížeč cookie zahodí."
            )

        return issues

    def validate(self) -> None:
        issues = self.problems()
        if issues:
            raise ConfigError(
                "Neplatná konfigurace pro prostředí '%s':\n  - %s" % (self.environment, "\n  - ".join(issues))
            )

    def safe_summary(self) -> dict:
        """Loggable snapshot — never contains secrets."""
        return {
            "environment": self.environment,
            "db_name": self.db_name,
            "mongo_host": _redact_mongo_url(self.mongo_url),
            "cookie_secure": self.cookie_secure,
            "cookie_samesite": self.cookie_samesite,
            "cors_origins": self.cors_origins or ["<same-origin only>"],
            "teltonika": f"{self.teltonika_host}:{self.teltonika_port}" if self.teltonika_enabled else "disabled",
            "allow_mock_data": self.allow_mock_data,
            "jwt_secret_configured": bool(self.jwt_secret),
        }


settings = Settings()
