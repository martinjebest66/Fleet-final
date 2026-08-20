"""API-level tests: authentication, authorisation and the GPS ingest path.

The application is exercised through FastAPI's TestClient with an in-memory
MongoDB, so these run without a database server or a deployed instance.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import server
import trips as trips_service
from teltonika import build_avl_packet, parse_avl_packet

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "test-admin-password-1234"


@pytest.fixture
def app_db(monkeypatch):
    """Point the application at a fresh in-memory database."""
    db = AsyncMongoMockClient()["fleet_api_test"]
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "_login_attempts", {})
    return db


def run(coro):
    """Run a coroutine on a throw-away loop (for seeding fixtures)."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def client(app_db):
    # Constructed without the context manager on purpose: the startup hook
    # connects to a real MongoDB, seeds the admin and binds the Teltonika TCP
    # port, none of which the HTTP surface under test needs.
    return TestClient(server.app, raise_server_exceptions=False)


@pytest.fixture
def admin(app_db):
    run(app_db.users.insert_one({
        "user_id": "user_admin",
        "email": ADMIN_EMAIL,
        "name": "Admin",
        "password_hash": server.hash_password(ADMIN_PASSWORD),
        "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    return {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}


# ── authentication ──────────────────────────────────────────────

def test_protected_endpoints_require_authentication(client):
    for path in ("/api/vehicles", "/api/logbook", "/api/reports/dashboard",
                 "/api/reports/trips", "/api/gps/trips", "/api/gps/devices"):
        response = client.get(path)
        assert response.status_code == 401, f"{path} vrátil {response.status_code}"


def test_public_endpoints_do_not_require_authentication(client, app_db):
    assert client.get("/api/").status_code == 200
    assert client.get("/api/auth/instructors-list").status_code == 200


def test_health_endpoint_is_public_and_reports_the_database(client):
    response = client.get("/api/health")

    # No real MongoDB behind the TestClient, so the probe reports "degraded"
    # with 503 — which is exactly what it must do for an orchestrator.
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["database"] in ("up", "down")
    assert "version" in body


def test_login_with_wrong_password_is_rejected(client, admin):
    response = client.post("/api/auth/login",
                           json={"email": ADMIN_EMAIL, "password": "wrong"})

    assert response.status_code == 401
    assert "access_token" not in response.cookies


def test_login_does_not_reveal_whether_an_account_exists(client, admin):
    unknown = client.post("/api/auth/login",
                          json={"email": "nobody@test.local", "password": "x" * 12})
    wrong = client.post("/api/auth/login",
                        json={"email": ADMIN_EMAIL, "password": "x" * 12})

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_successful_login_sets_a_usable_session_cookie(client, admin):
    response = client.post("/api/auth/login",
                           json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})

    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    cookie_header = response.headers.get("set-cookie", "")
    assert "access_token=" in cookie_header
    assert "HttpOnly" in cookie_header
    # Default deployment is same-origin over HTTP: a Secure cookie would be
    # discarded by the browser and every later request would come back 401.
    assert "SameSite=lax" in cookie_header
    assert "Secure" not in cookie_header

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN_EMAIL


def test_repeated_failed_logins_are_rate_limited(client, admin):
    limit = server.settings.login_rate_limit_attempts
    statuses = [
        client.post("/api/auth/login",
                    json={"email": ADMIN_EMAIL, "password": "wrong"}).status_code
        for _ in range(limit + 2)
    ]

    assert statuses[0] == 401
    assert 429 in statuses, "brute-force ochrana nezasáhla"


def test_logout_clears_the_session(client, admin):
    client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401


def test_an_expired_token_is_not_accepted(client, admin):
    import jwt

    expired = jwt.encode(
        {"sub": "user_admin", "role": "admin", "type": "access",
         "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        server.get_jwt_secret(), algorithm=server.JWT_ALGORITHM,
    )

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_a_token_signed_with_another_secret_is_not_accepted(client, admin):
    import jwt

    forged = jwt.encode(
        {"sub": "user_admin", "role": "admin", "type": "access",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "some-other-secret", algorithm="HS256",
    )

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_a_refresh_token_cannot_be_used_as_an_access_token(client, admin):
    refresh = server.create_refresh_token("user_admin")

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert response.status_code == 401


# ── authorisation ───────────────────────────────────────────────

def test_instructor_cannot_perform_admin_actions(client, app_db, admin):
    token = server.create_access_token("inst_1", "instructor")
    headers = {"Authorization": f"Bearer {token}"}

    run(app_db.instructors.insert_one({
        "instructor_id": "inst_1", "name": "Instruktor", "email": "i@test.local",
        "phone": "123", "license_number": "L1", "assigned_vehicle_ids": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }))

    forbidden = client.post("/api/vehicles", headers=headers, json={
        "registration_plate": "1AB 2345", "brand": "Škoda", "model": "Fabia", "year": 2020,
    })
    assert forbidden.status_code == 403

    # Reading is still allowed for an instructor.
    assert client.get("/api/vehicles", headers=headers).status_code == 200


def test_instructor_pins_are_never_returned_by_the_api(client, app_db, admin):
    run(app_db.instructors.insert_one({
        "instructor_id": "inst_pin", "name": "S PINem", "email": "p@test.local",
        "phone": "1", "license_number": "L", "assigned_vehicle_ids": [],
        "pin": server.hash_password("1234"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }))
    client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})

    body = client.get("/api/instructors").json()

    assert body[0]["has_pin"] is True
    assert "pin" not in body[0]
    assert "1234" not in str(body)


def test_public_login_list_exposes_only_names(client, app_db):
    run(app_db.instructors.insert_one({
        "instructor_id": "inst_pin", "name": "S PINem", "email": "secret@test.local",
        "phone": "777888999", "license_number": "L", "pin": "hash",
        "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
    }))

    body = client.get("/api/auth/instructors-list").json()

    assert body[0]["name"] == "S PINem"
    assert "email" not in body[0]
    assert "pin" not in body[0]
    assert "phone" not in body[0]


# ── password and PIN handling ───────────────────────────────────

def test_passwords_are_stored_as_bcrypt_hashes():
    hashed = server.hash_password("nejake-heslo")

    assert hashed.startswith("$2")
    assert "nejake-heslo" not in hashed
    assert server.verify_password("nejake-heslo", hashed) is True
    assert server.verify_password("jine-heslo", hashed) is False


def test_verify_password_tolerates_a_corrupt_stored_value():
    assert server.verify_password("x", "not-a-hash") is False
    assert server.verify_password("x", "") is False


async def test_a_legacy_plaintext_pin_is_upgraded_on_first_use(mock_db, monkeypatch):
    monkeypatch.setattr(server, "db", mock_db)
    await mock_db.instructors.insert_one({
        "instructor_id": "inst_legacy", "name": "Starý PIN", "pin": "4321",
    })
    instructor = await mock_db.instructors.find_one({"instructor_id": "inst_legacy"}, {"_id": 0})

    assert await server.verify_instructor_pin(instructor, "1111") is False
    assert await server.verify_instructor_pin(instructor, "4321") is True

    stored = await mock_db.instructors.find_one({"instructor_id": "inst_legacy"}, {"_id": 0})
    assert stored["pin"].startswith("$2")
    assert await server.verify_instructor_pin(stored, "4321") is True


# ── GPS ingest ──────────────────────────────────────────────────

async def test_tracker_records_are_stored_against_the_mapped_vehicle(mock_db, monkeypatch):
    monkeypatch.setattr(server, "db", mock_db)
    await mock_db.gps_devices.insert_one({
        "device_id": "dev_1", "imei": "352093081452251", "vehicle_id": "veh_1",
    })
    records = parse_avl_packet(build_avl_packet([
        {"lat": 50.0755, "lng": 14.4378, "speed": 45, "ts_ms": 1_772_000_000_000,
         "io": {239: (1, 1)}},
        {"lat": 50.0855, "lng": 14.4478, "speed": 50, "ts_ms": 1_772_000_010_000,
         "io": {239: (1, 1)}},
    ]))

    await server.on_teltonika_records("352093081452251", records)

    stored = await mock_db.vehicle_positions.find({}, {"_id": 0}).to_list(10)
    assert len(stored) == 2
    assert all(p["vehicle_id"] == "veh_1" for p in stored)
    assert all(p["source"] == trips_service.SOURCE_TELTONIKA for p in stored)
    assert stored[0]["ignition"] is True

    device = await mock_db.gps_devices.find_one({"imei": "352093081452251"}, {"_id": 0})
    assert device["status"] == "online"
    assert device["last_seen"]


async def test_records_from_an_unregistered_imei_are_discarded(mock_db, monkeypatch):
    monkeypatch.setattr(server, "db", mock_db)
    records = parse_avl_packet(build_avl_packet([{"lat": 50.0, "lng": 14.0, "speed": 10}]))

    await server.on_teltonika_records("999999999999999", records)

    assert await mock_db.vehicle_positions.count_documents({}) == 0


async def test_positions_without_a_gps_fix_are_not_stored(mock_db, monkeypatch):
    """A tracker with no fix reports 0/0 and zero satellites."""
    monkeypatch.setattr(server, "db", mock_db)
    await mock_db.gps_devices.insert_one({
        "device_id": "dev_1", "imei": "352093081452251", "vehicle_id": "veh_1",
    })
    records = parse_avl_packet(build_avl_packet([
        {"lat": 0.0, "lng": 0.0, "speed": 0, "satellites": 0, "ts_ms": 1_772_000_000_000},
        {"lat": 50.07, "lng": 14.43, "speed": 30, "satellites": 8, "ts_ms": 1_772_000_010_000},
    ]))

    await server.on_teltonika_records("352093081452251", records)

    stored = await mock_db.vehicle_positions.find({}, {"_id": 0}).to_list(10)
    assert len(stored) == 1
    assert stored[0]["lat"] == pytest.approx(50.07, abs=1e-5)
