"""MongoDB access layer: connection handling, readiness and index management.

The application previously created the Motor client at import time and assumed
the server was already reachable. Under `docker compose up` MongoDB regularly
needs a few seconds longer than the app container, which meant the admin seed
silently failed and login was broken until a manual restart. Connection
readiness is therefore an explicit, retried, logged startup step.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import OperationFailure, PyMongoError

from config import settings

logger = logging.getLogger("fleet.db")

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            settings.mongo_url,
            serverSelectionTimeoutMS=settings.mongo_connect_timeout_ms,
            connectTimeoutMS=settings.mongo_connect_timeout_ms,
            tz_aware=False,
        )
    return _client


def get_db() -> AsyncIOMotorDatabase:
    global _db
    if _db is None:
        _db = get_client()[settings.db_name]
    return _db


def set_db(database: AsyncIOMotorDatabase) -> None:
    """Override the active database (used by tests with an in-memory Mongo)."""
    global _db
    _db = database


async def ping(timeout: float = 5.0) -> bool:
    """Return True when the server answers a ping within `timeout` seconds."""
    try:
        await asyncio.wait_for(get_client().admin.command("ping"), timeout=timeout)
        return True
    except (PyMongoError, asyncio.TimeoutError, OSError) as exc:
        logger.debug("MongoDB ping failed: %s", exc)
        return False


async def wait_until_ready() -> bool:
    """Block until MongoDB answers, retrying with a bounded backoff.

    Returns True on success. Never raises so the caller can decide whether an
    unreachable database is fatal.
    """
    attempts = max(1, settings.mongo_startup_retries)
    delay = max(0.1, settings.mongo_startup_retry_delay)
    for attempt in range(1, attempts + 1):
        if await ping():
            logger.info(
                "MongoDB connected (%s/%s) after %d attempt(s)",
                settings.safe_summary()["mongo_host"],
                settings.db_name,
                attempt,
            )
            return True
        if attempt < attempts:
            logger.warning(
                "MongoDB not reachable yet (attempt %d/%d) — retrying in %.1fs",
                attempt,
                attempts,
                delay,
            )
            await asyncio.sleep(delay)
    logger.error(
        "MongoDB unreachable after %d attempts (%s)", attempts, settings.safe_summary()["mongo_host"]
    )
    return False


async def close() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


# ── Indexes ─────────────────────────────────────────────────────
# (collection, keys, kwargs). Unique indexes are only declared where the value
# is genuinely unique by construction; everything else stays non-unique so an
# existing production database with historical duplicates still starts.
INDEX_SPECS: List[Tuple[str, List[Tuple[str, int]], Dict[str, Any]]] = [
    ("users", [("email", 1)], {"unique": True, "name": "uniq_email"}),
    ("users", [("user_id", 1)], {"unique": True, "name": "uniq_user_id"}),
    ("user_sessions", [("session_token", 1)], {"unique": True, "name": "uniq_session_token"}),
    ("user_sessions", [("user_id", 1)], {"name": "idx_user"}),
    ("instructors", [("instructor_id", 1)], {"unique": True, "name": "uniq_instructor_id"}),
    ("vehicles", [("vehicle_id", 1)], {"unique": True, "name": "uniq_vehicle_id"}),
    ("vehicles", [("registration_plate", 1)], {"name": "idx_plate"}),
    ("vehicles", [("reservation_alias", 1)], {"name": "idx_reservation_alias"}),
    ("gps_devices", [("imei", 1)], {"unique": True, "name": "uniq_imei"}),
    ("gps_devices", [("vehicle_id", 1)], {"name": "idx_vehicle"}),
    # Position stream: the hot query is "positions of one vehicle in a window".
    ("vehicle_positions", [("vehicle_id", 1), ("timestamp", 1)], {"name": "idx_vehicle_time"}),
    ("vehicle_positions", [("timestamp", 1)], {"name": "idx_time"}),
    # Trips are reported per vehicle and period, from every source.
    ("gps_trips", [("trip_id", 1)], {"unique": True, "name": "uniq_trip_id"}),
    ("gps_trips", [("vehicle_id", 1), ("start_time", 1)], {"name": "idx_vehicle_start"}),
    ("gps_trips", [("start_time", 1)], {"name": "idx_start"}),
    ("gps_trips", [("source", 1), ("start_time", 1)], {"name": "idx_source_start"}),
    ("logbook", [("entry_id", 1)], {"unique": True, "name": "uniq_entry_id"}),
    ("logbook", [("vehicle_id", 1), ("date", 1)], {"name": "idx_vehicle_date"}),
    ("logbook", [("date", 1)], {"name": "idx_date"}),
    ("logbook", [("instructor_id", 1), ("date", 1)], {"name": "idx_instructor_date"}),
    ("fuel_entries", [("vehicle_id", 1), ("date", 1)], {"name": "idx_vehicle_date"}),
    ("fuel_entries", [("date", 1)], {"name": "idx_date"}),
    ("damage_reports", [("vehicle_id", 1)], {"name": "idx_vehicle"}),
    ("damage_reports", [("status", 1)], {"name": "idx_status"}),
    ("qr_handovers", [("vehicle_id", 1), ("created_at", -1)], {"name": "idx_vehicle_created"}),
    ("maintenance", [("vehicle_id", 1)], {"name": "idx_vehicle"}),
    ("reservation_drives", [("drive_id", 1)], {"unique": True, "name": "uniq_drive_id"}),
    ("reservation_drives", [("vehicle_id", 1), ("date", 1)], {"name": "idx_vehicle_date"}),
    ("reservation_drives", [("batch_id", 1)], {"name": "idx_batch"}),
    ("vehicle_obd", [("vehicle_id", 1)], {"name": "idx_vehicle"}),
    ("app_settings", [("key", 1)], {"unique": True, "name": "uniq_key"}),
]

# Idempotent trip import: at most one trip per (source, external_id). Partial so
# documents without an external_id (Teltonika, manual) are unaffected.
PARTIAL_INDEX_SPECS: List[Tuple[str, List[Tuple[str, int]], Dict[str, Any]]] = [
    (
        "gps_trips",
        [("source", 1), ("external_id", 1)],
        {
            "unique": True,
            "name": "uniq_source_external_id",
            "partialFilterExpression": {"external_id": {"$type": "string"}},
        },
    ),
]

# Position ingest de-duplication: a tracker that reconnects replays records it
# did not get an ACK for. Partial so legacy documents without an `imei` (mock or
# imported data) never collide.
DEDUP_INDEX_SPECS: List[Tuple[str, List[Tuple[str, int]], Dict[str, Any]]] = [
    (
        "vehicle_positions",
        [("imei", 1), ("timestamp", 1)],
        {
            "unique": True,
            "name": "uniq_imei_timestamp",
            "partialFilterExpression": {"imei": {"$type": "string"}},
        },
    ),
]


async def ensure_indexes(database: Optional[AsyncIOMotorDatabase] = None) -> Dict[str, List[str]]:
    """Create the indexes the application relies on.

    A failure to build one index (typically a unique index rejected because of
    pre-existing duplicates) is logged with the offending collection and never
    aborts startup — the app must keep serving a legacy database.
    """
    db = database if database is not None else get_db()
    created: List[str] = []
    failed: List[str] = []

    for collection, keys, kwargs in INDEX_SPECS + PARTIAL_INDEX_SPECS + DEDUP_INDEX_SPECS:
        label = f"{collection}.{kwargs.get('name', keys)}"
        try:
            await db[collection].create_index(keys, **kwargs)
            created.append(label)
        except OperationFailure as exc:
            failed.append(label)
            logger.warning(
                "Index %s nebyl vytvořen (%s). Pravděpodobně existují duplicitní historická data — "
                "aplikace pokračuje bez tohoto indexu.",
                label,
                exc.details.get("errmsg", str(exc)) if getattr(exc, "details", None) else exc,
            )
        except PyMongoError as exc:
            failed.append(label)
            logger.warning("Index %s nebyl vytvořen: %s", label, exc)

    # TTL index for expired sessions — expires_at is stored as an ISO string in
    # legacy documents, so this only helps new datetime-valued documents; the
    # explicit expiry check in the auth layer remains authoritative.
    try:
        await db.user_sessions.create_index("expires_at_dt", expireAfterSeconds=0, name="ttl_expires")
        created.append("user_sessions.ttl_expires")
    except PyMongoError as exc:
        logger.debug("Session TTL index skipped: %s", exc)

    logger.info("Indexy připraveny: %d vytvořeno/ověřeno, %d selhalo", len(created), len(failed))
    return {"created": created, "failed": failed}
