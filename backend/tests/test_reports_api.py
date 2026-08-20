"""Report endpoints, exercised over HTTP.

Complements `test_trip_reporting.py`: the same guarantees, but through the API
the frontend actually calls, so a wiring mistake between the service layer and
the endpoints is caught too.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import server
from trips import SOURCE_RUHAVIK, SOURCE_TELTONIKA

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "test-admin-password-1234"
VEHICLE = "veh_1"
OTHER_VEHICLE = "veh_2"


def run(coro):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def trip(trip_id, source, day, hour=8, distance_m=12000, vehicle_id=VEHICLE, **extra):
    start = datetime(2026, 3, day, hour, 0, tzinfo=timezone.utc)
    doc = {
        "trip_id": trip_id,
        "vehicle_id": vehicle_id,
        "source": source,
        "start_time": start.replace(tzinfo=None).isoformat(),
        "end_time": (start + timedelta(minutes=40)).replace(tzinfo=None).isoformat(),
        "start_location": {"lat": 50.07, "lng": 14.43, "address": "Start"},
        "end_location": {"lat": 50.10, "lng": 14.50, "address": "Cíl"},
        "route_points": [{"lat": 50.07 + i / 1000, "lng": 14.43, "timestamp": ""} for i in range(50)],
        "distance": distance_m,
        "max_speed": 80,
        "avg_speed": 40,
        "synced_to_logbook": False,
        "duplicate_of": None,
        "created_at": start.isoformat(),
    }
    doc.update(extra)
    return doc


@pytest.fixture
def client(monkeypatch):
    db = AsyncMongoMockClient()["fleet_reports_test"]
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "_login_attempts", {})

    run(db.users.insert_one({
        "user_id": "user_admin", "email": ADMIN_EMAIL, "name": "Admin",
        "password_hash": server.hash_password(ADMIN_PASSWORD), "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    run(db.vehicles.insert_many([
        {"vehicle_id": VEHICLE, "brand": "Škoda", "model": "Fabia",
         "registration_plate": "1AB 2345", "odometer": 10000,
         "assigned_instructor_id": "inst_1", "fuel_type": "benzín", "year": 2020,
         "qr_code_fuel": "f", "qr_code_damage": "d", "qr_code_handover": "h",
         "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"},
        {"vehicle_id": OTHER_VEHICLE, "brand": "VW", "model": "Golf",
         "registration_plate": "2CD 6789", "odometer": 20000,
         "assigned_instructor_id": None, "fuel_type": "nafta", "year": 2021,
         "qr_code_fuel": "f2", "qr_code_damage": "d2", "qr_code_handover": "h2",
         "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"},
    ]))
    run(db.instructors.insert_one({
        "instructor_id": "inst_1", "name": "Jan Novák", "email": "jan@test.local",
        "phone": "1", "license_number": "L1", "assigned_vehicle_ids": [VEHICLE],
        "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
    }))

    api = TestClient(server.app, raise_server_exceptions=False)
    api.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    api.db = db
    return api


@pytest.fixture
def mixed_trips(client):
    run(client.db.gps_trips.insert_many([
        trip("t1", SOURCE_TELTONIKA, 2, distance_m=12000),
        trip("t2", SOURCE_TELTONIKA, 3, distance_m=8000),
        trip("r1", SOURCE_RUHAVIK, 4, distance_m=15000, external_id="ruhavik:1"),
        trip("r2", SOURCE_RUHAVIK, 5, distance_m=5000, external_id="ruhavik:2",
             vehicle_id=OTHER_VEHICLE),
    ]))
    run(client.db.logbook.insert_one({
        "entry_id": "l1", "vehicle_id": VEHICLE, "instructor_id": "inst_1",
        "date": "2026-03-06", "start_time": "09:00", "end_time": "10:00",
        "start_location": "A", "end_location": "B", "route_description": "A->B",
        "start_odometer": 1000, "end_odometer": 1010, "distance": 10,
        "purpose": "výcvik", "gps_source": False, "created_at": "2026-03-06T00:00:00",
    }))
    return client


def test_trip_report_covers_every_source(mixed_trips):
    body = mixed_trips.get(
        "/api/reports/trips?date_from=2026-03-01&date_to=2026-03-31"
    ).json()

    assert body["summary"]["total_trips"] == 5
    assert body["summary"]["total_distance_km"] == pytest.approx(12 + 8 + 15 + 5 + 10)
    assert body["summary"]["by_source"][SOURCE_RUHAVIK]["trips"] == 2
    assert {t["source"] for t in body["trips"]} == {SOURCE_TELTONIKA, SOURCE_RUHAVIK, "manual"}


def test_km_stats_covers_every_source(mixed_trips):
    body = mixed_trips.get(
        "/api/reports/km-stats?date_from=2026-03-01&date_to=2026-03-31"
    ).json()

    assert body["total_km"] == pytest.approx(50.0)
    assert body["total_trips"] == 5
    assert body["vehicle_stats"][VEHICLE]["total_km"] == pytest.approx(45.0)
    assert body["vehicle_stats"][OTHER_VEHICLE]["total_km"] == pytest.approx(5.0)


def test_km_stats_filtered_to_one_vehicle_keeps_ruhavik(mixed_trips):
    body = mixed_trips.get(
        f"/api/reports/km-stats?date_from=2026-03-01&date_to=2026-03-31&vehicle_id={OTHER_VEHICLE}"
    ).json()

    assert body["total_trips"] == 1
    assert body["by_source"] == {SOURCE_RUHAVIK: {"trips": 1, "distance_km": 5.0}}


def test_period_filter_narrows_every_source(mixed_trips):
    body = mixed_trips.get(
        "/api/reports/trips?date_from=2026-03-04&date_to=2026-03-05"
    ).json()

    assert {t["trip_id"] for t in body["trips"]} == {"r1", "r2"}


def test_source_filter_is_opt_in(mixed_trips):
    ruhavik_only = mixed_trips.get("/api/reports/trips?source=ruhavik").json()
    assert {t["trip_id"] for t in ruhavik_only["trips"]} == {"r1", "r2"}

    tracker_only = mixed_trips.get("/api/reports/trips?source=teltonika").json()
    assert {t["trip_id"] for t in tracker_only["trips"]} == {"t1", "t2"}


def test_unknown_source_filter_is_a_client_error(mixed_trips):
    response = mixed_trips.get("/api/reports/trips?source=nesmysl")

    assert response.status_code == 400
    assert "nesmysl" in response.json()["detail"]


def test_dashboard_counts_ruhavik_trips(client):
    today = datetime.now(timezone.utc)
    run(client.db.gps_trips.insert_many([
        {**trip("t_now", SOURCE_TELTONIKA, 2, distance_m=10000),
         "start_time": today.replace(tzinfo=None).isoformat(),
         "end_time": (today + timedelta(minutes=30)).replace(tzinfo=None).isoformat()},
        {**trip("r_now", SOURCE_RUHAVIK, 2, distance_m=20000, external_id="ruhavik:now"),
         "start_time": today.replace(tzinfo=None).isoformat(),
         "end_time": (today + timedelta(minutes=30)).replace(tzinfo=None).isoformat()},
    ]))

    body = client.get("/api/reports/dashboard").json()

    assert body["trips_month"] == 2
    assert body["total_km_month"] == 30
    assert set(body["km_month_by_source"]) == {SOURCE_TELTONIKA, SOURCE_RUHAVIK}


def test_vehicle_report_covers_every_source(mixed_trips):
    body = mixed_trips.get(f"/api/reports/vehicle/{VEHICLE}").json()

    assert body["summary"]["total_trips"] == 4    # 2 tracker + 1 ruhavik + 1 manual
    assert body["summary"]["by_source"][SOURCE_RUHAVIK]["trips"] == 1


def test_instructor_report_attributes_gps_and_ruhavik_drives(mixed_trips):
    body = mixed_trips.get("/api/reports/instructor/inst_1").json()

    assert body["instructor_name"] == "Jan Novák"
    # The vehicle is assigned to this instructor, so tracker and Ruhavik drives
    # count towards them, not only the hand-written logbook row.
    assert body["summary"]["total_trips"] == 4
    assert body["summary"]["by_source"][SOURCE_RUHAVIK]["trips"] == 1


def test_csv_export_lists_every_source_and_totals(mixed_trips):
    response = mixed_trips.get(
        "/api/reports/trips/export-csv?date_from=2026-03-01&date_to=2026-03-31"
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")
    assert "ruhavik" in text
    assert "teltonika" in text
    assert "Celkem jizd;5" in text
    assert "Celkem km;50,0" in text


def test_logbook_pdf_export_includes_imported_drives(mixed_trips):
    response = mixed_trips.get(
        "/api/logbook/export-pdf?date_from=2026-03-01&date_to=2026-03-31"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1000


def test_gps_trip_list_honours_the_date_filter(mixed_trips):
    """The filter used to be accepted and ignored, returning the whole history."""
    body = mixed_trips.get("/api/gps/trips?date_from=2026-03-04&date_to=2026-03-04").json()

    assert [t["trip_id"] for t in body] == ["r1"]


def test_gps_trip_list_omits_route_points_by_default(mixed_trips):
    body = mixed_trips.get("/api/gps/trips").json()

    assert all(t["route_points"] == [] for t in body)

    with_route = mixed_trips.get("/api/gps/trips?include_route=true").json()
    assert any(t["route_points"] for t in with_route)


def test_trip_route_is_downsampled_for_the_map_only(mixed_trips):
    body = mixed_trips.get("/api/gps/trips/t1/route?max_points=10").json()

    assert len(body["points"]) == 10
    assert body["total_points"] == 50
    assert body["downsampled"] is True

    # The stored history itself is untouched.
    stored = run(mixed_trips.db.gps_trips.find_one({"trip_id": "t1"}, {"_id": 0}))
    assert len(stored["route_points"]) == 50


def test_duplicate_trips_are_excluded_from_the_report_but_retrievable(client):
    run(client.db.gps_trips.insert_many([
        trip("t1", SOURCE_TELTONIKA, 2, distance_m=12000),
        trip("r1", SOURCE_RUHAVIK, 2, distance_m=12100, external_id="ruhavik:dup",
             duplicate_of="t1"),
    ]))

    default = client.get("/api/reports/trips?date_from=2026-03-01&date_to=2026-03-31").json()
    assert default["summary"]["total_trips"] == 1
    assert default["summary"]["total_distance_km"] == 12.0

    including = client.get(
        "/api/reports/trips?date_from=2026-03-01&date_to=2026-03-31&include_duplicates=true"
    ).json()
    assert including["summary"]["total_trips"] == 2


def test_mock_generators_are_refused_in_production_configuration(client, monkeypatch):
    monkeypatch.setattr(server.settings, "allow_mock_data", False)

    assert client.post(f"/api/gps/import-mock?vehicle_id={VEHICLE}").status_code == 403
    assert client.post("/api/gps/simulate-live").status_code == 403


def test_ruhavik_upload_endpoint_reports_new_and_duplicate_drives(client):
    csv = (
        "id,start time,end time,distance,max speed\n"
        "trip-1,2026-03-02 08:00:00,2026-03-02 08:30:00,12.4,84\n"
        "trip-2,2026-03-02 14:00:00,2026-03-02 14:45:00,25.0,101\n"
    )
    files = {"file": ("export.csv", csv, "text/csv")}

    first = client.post("/api/gps/import-ruhavik", data={"vehicle_id": VEHICLE}, files=files)
    assert first.status_code == 200
    assert first.json()["imported"] == 2

    files = {"file": ("export.csv", csv, "text/csv")}
    second = client.post("/api/gps/import-ruhavik", data={"vehicle_id": VEHICLE}, files=files)
    assert second.json()["imported"] == 0
    assert second.json()["skipped_already_imported"] == 2

    # Both uploads together still produce two drives in the report.
    report = client.get("/api/reports/trips?date_from=2026-03-01&date_to=2026-03-31").json()
    assert report["summary"]["total_trips"] == 2
    assert report["summary"]["by_source"][SOURCE_RUHAVIK]["distance_km"] == pytest.approx(37.4)


def test_ruhavik_upload_rejects_an_unknown_vehicle(client):
    files = {"file": ("export.csv", "id,start time,end time,distance\n", "text/csv")}

    response = client.post("/api/gps/import-ruhavik", data={"vehicle_id": "nope"}, files=files)

    assert response.status_code == 404


def test_ruhavik_upload_reports_partially_broken_files(client):
    csv = (
        "id,start time,end time,distance\n"
        "ok-1,2026-03-02 08:00:00,2026-03-02 08:30:00,12.4\n"
        "bad-1,rubbish,2026-03-02 09:30:00,5.0\n"
        "ok-2,2026-03-02 14:00:00,2026-03-02 14:45:00,25.0\n"
    )
    files = {"file": ("mixed.csv", csv, "text/csv")}

    body = client.post("/api/gps/import-ruhavik", data={"vehicle_id": VEHICLE}, files=files).json()

    assert body["imported"] == 2
    assert body["rejected"] == 1
    assert body["errors"]
