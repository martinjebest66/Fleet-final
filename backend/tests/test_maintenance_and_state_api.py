"""API tests for photographed maintenance documents and vehicle state history."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import server

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "test-admin-password-1234"
VEHICLE = "veh_1"

# Smallest thing that is unambiguously a JPEG.
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 64 + b"\xff\xd9"
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


def run(coro):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def client(monkeypatch):
    db = AsyncMongoMockClient()["fleet_docs_test"]
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "_login_attempts", {})

    run(db.users.insert_one({
        "user_id": "user_admin", "email": ADMIN_EMAIL, "name": "Admin",
        "password_hash": server.hash_password(ADMIN_PASSWORD), "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    run(db.vehicles.insert_one({
        "vehicle_id": VEHICLE, "brand": "Škoda", "model": "Fabia",
        "registration_plate": "1AB 2345", "odometer": 41000, "year": 2021,
        "fuel_type": "benzín", "qr_code_fuel": "f", "qr_code_damage": "d",
        "qr_code_handover": "h", "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }))

    api = TestClient(server.app, raise_server_exceptions=False)
    api.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    api.db = db
    return api


@pytest.fixture
def maintenance_id(client):
    response = client.post("/api/maintenance", json={
        "vehicle_id": VEHICLE, "type": "STK",
        "last_done_date": "2026-01-15", "next_due_date": "2028-01-15",
    })
    assert response.status_code == 200
    return response.json()["maintenance_id"]


# ── photographed service / maintenance documents ────────────────

def test_document_upload_and_retrieval(client, maintenance_id):
    upload = client.post(
        f"/api/maintenance/{maintenance_id}/documents",
        files={"file": ("stk.jpg", JPEG, "image/jpeg")},
        data={"doc_type": "STK protokol", "label": "STK 2026"},
    )
    assert upload.status_code == 200
    document = upload.json()
    assert document["doc_type"] == "STK protokol"
    assert document["label"] == "STK 2026"
    assert document["size_bytes"] == len(JPEG)
    assert document["uploaded_by"] == ADMIN_EMAIL

    fetched = client.get(document["url"])
    assert fetched.status_code == 200
    assert fetched.headers["content-type"].startswith("image/jpeg")
    assert fetched.content == JPEG          # stored byte-for-byte


def test_documents_appear_on_the_maintenance_record(client, maintenance_id):
    client.post(f"/api/maintenance/{maintenance_id}/documents",
                files={"file": ("faktura.jpg", JPEG, "image/jpeg")},
                data={"doc_type": "faktura"})

    listed = client.get("/api/maintenance").json()
    assert len(listed[0]["documents"]) == 1
    assert listed[0]["documents"][0]["doc_type"] == "faktura"

    detail = client.get(f"/api/maintenance/{maintenance_id}").json()
    assert len(detail["documents"]) == 1


def test_the_image_bytes_never_travel_with_the_list(client, maintenance_id):
    """A few phone photos must not bloat every maintenance list response."""
    big = b"\xff\xd8\xff\xe0" + b"x" * 400_000 + b"\xff\xd9"
    client.post(f"/api/maintenance/{maintenance_id}/documents",
                files={"file": ("velka.jpg", big, "image/jpeg")},
                data={"doc_type": "foto"})

    listed = client.get("/api/maintenance")

    assert listed.status_code == 200
    assert len(listed.content) < 5_000
    assert listed.json()[0]["documents"][0]["size_bytes"] == len(big)


def test_pdf_invoices_are_accepted(client, maintenance_id):
    response = client.post(f"/api/maintenance/{maintenance_id}/documents",
                           files={"file": ("faktura.pdf", PDF, "application/pdf")},
                           data={"doc_type": "faktura"})

    assert response.status_code == 200
    assert client.get(response.json()["url"]).headers["content-type"].startswith("application/pdf")


def test_executables_are_rejected(client, maintenance_id):
    response = client.post(f"/api/maintenance/{maintenance_id}/documents",
                           files={"file": ("x.exe", b"MZ\x90", "application/x-msdownload")})

    assert response.status_code == 415


def test_oversized_upload_is_rejected(client, maintenance_id, monkeypatch):
    monkeypatch.setattr(server.settings, "max_upload_bytes", 1024)

    response = client.post(f"/api/maintenance/{maintenance_id}/documents",
                           files={"file": ("velka.jpg", b"\xff\xd8" + b"x" * 5000, "image/jpeg")})

    assert response.status_code == 413


def test_unknown_document_type_falls_back_instead_of_failing(client, maintenance_id):
    response = client.post(f"/api/maintenance/{maintenance_id}/documents",
                           files={"file": ("x.jpg", JPEG, "image/jpeg")},
                           data={"doc_type": "vymyšlený typ"})

    assert response.status_code == 200
    assert response.json()["doc_type"] == "jiné"


def test_document_upload_requires_authentication(client, maintenance_id):
    client.cookies.clear()

    response = client.post(f"/api/maintenance/{maintenance_id}/documents",
                           files={"file": ("x.jpg", JPEG, "image/jpeg")})

    assert response.status_code == 401


def test_document_download_requires_authentication(client, maintenance_id):
    url = client.post(f"/api/maintenance/{maintenance_id}/documents",
                      files={"file": ("x.jpg", JPEG, "image/jpeg")}).json()["url"]
    client.cookies.clear()

    assert client.get(url).status_code == 401


def test_upload_to_an_unknown_maintenance_record_is_404(client):
    response = client.post("/api/maintenance/mnt_nope/documents",
                           files={"file": ("x.jpg", JPEG, "image/jpeg")})

    assert response.status_code == 404


def test_deleting_a_document(client, maintenance_id):
    document_id = client.post(f"/api/maintenance/{maintenance_id}/documents",
                              files={"file": ("x.jpg", JPEG, "image/jpeg")}).json()["document_id"]

    assert client.delete(f"/api/maintenance/documents/{document_id}").status_code == 200
    assert client.get("/api/maintenance").json()[0]["documents"] == []
    assert client.delete(f"/api/maintenance/documents/{document_id}").status_code == 404


def test_deleting_the_record_takes_its_documents_with_it(client, maintenance_id):
    client.post(f"/api/maintenance/{maintenance_id}/documents",
                files={"file": ("x.jpg", JPEG, "image/jpeg")})

    response = client.delete(f"/api/maintenance/{maintenance_id}")

    assert response.json()["documents_deleted"] == 1
    assert run(client.db.maintenance_documents.count_documents({})) == 0


def test_summary_endpoint_is_not_shadowed_by_the_id_route(client, maintenance_id):
    """/maintenance/summary must not be read as a maintenance id."""
    response = client.get("/api/maintenance/summary")

    assert response.status_code == 200
    assert response.json()["total"] == 1


# ── vehicle state ───────────────────────────────────────────────

@pytest.fixture
def vehicle_history(client):
    run(client.db.fuel_entries.insert_one({
        "fuel_id": "fuel_1", "vehicle_id": VEHICLE, "date": "2026-03-01",
        "odometer": 41000, "liters": 40.0, "price_per_liter": 37.5,
        "total_price": 1500.0, "created_at": "2026-03-01T12:00:00",
    }))
    run(client.db.vehicle_positions.insert_many([
        {"vehicle_id": VEHICLE, "lat": 50.0, "lng": 14.0, "speed": 40,
         "timestamp": f"2026-03-0{day}T{hour:02d}:00:00+00:00", "source": "teltonika",
         "obd": {"total_odometer": odo, "fuel_level": fuel}}
        for day, hour, odo, fuel in [
            (1, 13, 500_000, 95), (2, 10, 515_000, 80), (3, 10, 540_000, 60),
        ]
    ]))
    return client


def test_state_at_a_date(vehicle_history):
    response = vehicle_history.get(f"/api/vehicles/{VEHICLE}/state?at=2026-03-02")

    assert response.status_code == 200
    body = response.json()
    assert body["odometer_km"] == 41015          # 41000 + 15 km per the tracker
    assert body["odometer_is_estimate"] is True
    assert body["odometer_source"] == "fuel"
    assert body["fuel_level_percent"] == 80
    assert body["last_refuel"]["liters"] == 40.0


def test_state_moves_with_the_chosen_date(vehicle_history):
    day2 = vehicle_history.get(f"/api/vehicles/{VEHICLE}/state?at=2026-03-02").json()
    day3 = vehicle_history.get(f"/api/vehicles/{VEHICLE}/state?at=2026-03-03").json()

    assert day3["odometer_km"] > day2["odometer_km"]
    assert day3["fuel_level_percent"] < day2["fuel_level_percent"]


def test_state_history_returns_a_daily_rollup(vehicle_history):
    response = vehicle_history.get(
        f"/api/vehicles/{VEHICLE}/state/history?date_from=2026-03-01&date_to=2026-03-03"
    )

    assert response.status_code == 200
    body = response.json()
    assert [row["date"] for row in body["daily"]] == ["2026-03-01", "2026-03-02", "2026-03-03"]
    assert body["daily"][-1]["odometer_km"] == 41040
    assert set(body["sources"]) == {"fuel", "gps"}


def test_state_history_thins_a_dense_tracker_stream_for_display(client):
    run(client.db.vehicle_positions.insert_many([
        {"vehicle_id": VEHICLE, "lat": 50.0, "lng": 14.0, "speed": 30,
         "timestamp": f"2026-03-01T{i // 60:02d}:{i % 60:02d}:00+00:00",
         "source": "teltonika", "obd": {"total_odometer": 500_000 + i * 100, "fuel_level": 90}}
        for i in range(600)
    ]))

    body = client.get(
        f"/api/vehicles/{VEHICLE}/state/history?date_from=2026-03-01&date_to=2026-03-01&max_points=50"
    ).json()

    assert body["total_readings"] == 600
    assert body["downsampled"] is True
    assert len(body["readings"]) <= 52
    # The stored history is untouched.
    assert run(client.db.vehicle_positions.count_documents({})) == 600


def test_state_of_an_unknown_vehicle_is_404(client):
    assert client.get("/api/vehicles/veh_nope/state").status_code == 404
    assert client.get("/api/vehicles/veh_nope/state/history").status_code == 404


def test_state_requires_authentication(vehicle_history):
    vehicle_history.cookies.clear()

    assert vehicle_history.get(f"/api/vehicles/{VEHICLE}/state").status_code == 401


def test_a_malformed_date_is_a_client_error(vehicle_history):
    response = vehicle_history.get(f"/api/vehicles/{VEHICLE}/state?at=vcera")

    assert response.status_code == 400


def test_state_route_does_not_shadow_the_vehicle_detail(client):
    """/vehicles/{id} must still work alongside /vehicles/{id}/state."""
    response = client.get(f"/api/vehicles/{VEHICLE}")

    assert response.status_code == 200
    assert response.json()["registration_plate"] == "1AB 2345"
