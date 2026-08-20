"""Unified trip reporting across every data source.

These tests pin down the behaviour the reports depend on: a drive counts once,
it counts regardless of where it came from, and the source is never lost.
"""

from datetime import datetime, timedelta, timezone

import pytest

import trips as trips_service
from trips import (
    SOURCE_MANUAL,
    SOURCE_MOCK,
    SOURCE_RUHAVIK,
    SOURCE_TELTONIKA,
    get_trips,
    looks_like_same_drive,
    summarize,
)

VEHICLE_A = "veh_aaa"
VEHICLE_B = "veh_bbb"


def gps_trip(trip_id, source, start, minutes=30, distance_m=12000, vehicle_id=VEHICLE_A, **extra):
    """Build a `gps_trips` document the way the application stores them."""
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(minutes=minutes)
    doc = {
        "trip_id": trip_id,
        "vehicle_id": vehicle_id,
        "source": source,
        "start_time": start_dt.replace(tzinfo=None).isoformat(),
        "end_time": end_dt.replace(tzinfo=None).isoformat(),
        "start_location": {"lat": 50.07, "lng": 14.43, "address": "A"},
        "end_location": {"lat": 50.10, "lng": 14.50, "address": "B"},
        "route_points": [],
        "distance": distance_m,
        "max_speed": 80,
        "avg_speed": 40,
        "synced_to_logbook": False,
        "duplicate_of": None,
        "created_at": start_dt.isoformat(),
    }
    doc.update(extra)
    return doc


def logbook_entry(entry_id, date, distance_km=10, vehicle_id=VEHICLE_A, gps_source=False):
    return {
        "entry_id": entry_id,
        "vehicle_id": vehicle_id,
        "instructor_id": None,
        "date": date,
        "start_time": "09:00",
        "end_time": "10:00",
        "start_location": "Praha",
        "end_location": "Kladno",
        "route_description": "Praha -> Kladno",
        "start_odometer": 1000,
        "end_odometer": 1000 + distance_km,
        "distance": distance_km,
        "purpose": "výcvik",
        "gps_source": gps_source,
        "created_at": "2026-01-01T00:00:00",
    }


# ── 1-3: a report holds one source, the other source, and both ──

async def test_report_contains_only_teltonika_trip(mock_db):
    await mock_db.gps_trips.insert_one(gps_trip("t1", SOURCE_TELTONIKA, "2026-03-02T08:00:00"))

    result = await get_trips(mock_db, date_from="2026-03-01", date_to="2026-03-31")
    summary = summarize(result)

    assert summary["total_trips"] == 1
    assert summary["total_distance_km"] == 12.0
    assert set(summary["by_source"]) == {SOURCE_TELTONIKA}


async def test_report_contains_only_ruhavik_trip(mock_db):
    await mock_db.gps_trips.insert_one(
        gps_trip("r1", SOURCE_RUHAVIK, "2026-03-04T08:00:00", distance_m=8000,
                 external_id="ruhavik:abc")
    )

    result = await get_trips(mock_db, date_from="2026-03-01", date_to="2026-03-31")
    summary = summarize(result)

    # A Ruhavik import is a real drive and must show up on its own, without a
    # single tracker record in the database.
    assert summary["total_trips"] == 1
    assert summary["total_distance_km"] == 8.0
    assert set(summary["by_source"]) == {SOURCE_RUHAVIK}


async def test_report_contains_both_sources(mock_db):
    await mock_db.gps_trips.insert_many([
        gps_trip("t1", SOURCE_TELTONIKA, "2026-03-02T08:00:00", distance_m=12000),
        gps_trip("r1", SOURCE_RUHAVIK, "2026-03-05T08:00:00", distance_m=8000,
                 external_id="ruhavik:abc"),
    ])
    await mock_db.logbook.insert_one(logbook_entry("l1", "2026-03-06", distance_km=5))

    result = await get_trips(mock_db, date_from="2026-03-01", date_to="2026-03-31")
    summary = summarize(result)

    assert summary["total_trips"] == 3
    assert summary["by_source"][SOURCE_TELTONIKA]["trips"] == 1
    assert summary["by_source"][SOURCE_RUHAVIK]["trips"] == 1
    assert summary["by_source"][SOURCE_MANUAL]["trips"] == 1


# ── 4-5: totals include every source ──

async def test_total_distance_sums_all_sources(mock_db):
    await mock_db.gps_trips.insert_many([
        gps_trip("t1", SOURCE_TELTONIKA, "2026-03-02T08:00:00", distance_m=12000),
        gps_trip("t2", SOURCE_TELTONIKA, "2026-03-03T08:00:00", distance_m=3500),
        gps_trip("r1", SOURCE_RUHAVIK, "2026-03-05T08:00:00", distance_m=8000,
                 external_id="ruhavik:1"),
    ])
    await mock_db.logbook.insert_one(logbook_entry("l1", "2026-03-06", distance_km=5))

    summary = summarize(await get_trips(mock_db, date_from="2026-03-01", date_to="2026-03-31"))

    assert summary["total_distance_km"] == pytest.approx(12.0 + 3.5 + 8.0 + 5.0)


async def test_trip_count_includes_all_sources(mock_db):
    await mock_db.gps_trips.insert_many([
        gps_trip(f"t{i}", SOURCE_TELTONIKA, f"2026-03-0{i}T08:00:00") for i in range(1, 4)
    ])
    await mock_db.gps_trips.insert_many([
        gps_trip(f"r{i}", SOURCE_RUHAVIK, f"2026-03-1{i}T08:00:00", external_id=f"ruhavik:{i}")
        for i in range(1, 3)
    ])

    summary = summarize(await get_trips(mock_db, date_from="2026-03-01", date_to="2026-03-31"))

    assert summary["total_trips"] == 5


# ── 6-7: filters apply to Ruhavik trips too ──

async def test_period_filter_includes_ruhavik(mock_db):
    await mock_db.gps_trips.insert_many([
        gps_trip("r_in", SOURCE_RUHAVIK, "2026-03-15T08:00:00", external_id="ruhavik:in"),
        gps_trip("r_out", SOURCE_RUHAVIK, "2026-04-15T08:00:00", external_id="ruhavik:out"),
    ])

    inside = await get_trips(mock_db, date_from="2026-03-01", date_to="2026-03-31")

    assert [t["trip_id"] for t in inside] == ["r_in"]


async def test_vehicle_filter_includes_ruhavik(mock_db):
    await mock_db.gps_trips.insert_many([
        gps_trip("r_a", SOURCE_RUHAVIK, "2026-03-15T08:00:00", vehicle_id=VEHICLE_A,
                 external_id="ruhavik:a"),
        gps_trip("r_b", SOURCE_RUHAVIK, "2026-03-15T08:00:00", vehicle_id=VEHICLE_B,
                 external_id="ruhavik:b"),
    ])

    only_a = await get_trips(mock_db, vehicle_id=VEHICLE_A)

    assert [t["trip_id"] for t in only_a] == ["r_a"]


# ── 9-10: duplicates counted once, distinct drives never merged ──

async def test_duplicate_trip_counted_once(mock_db):
    await mock_db.gps_trips.insert_many([
        gps_trip("t1", SOURCE_TELTONIKA, "2026-03-02T08:00:00", distance_m=12000),
        # The same drive, imported from Ruhavik and flagged during import.
        gps_trip("r1", SOURCE_RUHAVIK, "2026-03-02T08:00:00", distance_m=12100,
                 external_id="ruhavik:dup", duplicate_of="t1"),
    ])

    summary = summarize(await get_trips(mock_db))
    assert summary["total_trips"] == 1
    assert summary["total_distance_km"] == 12.0

    # The record is kept, and can be inspected on request.
    with_dupes = await get_trips(mock_db, include_duplicates=True)
    assert len(with_dupes) == 2
    assert {t["trip_id"] for t in with_dupes} == {"t1", "r1"}


def test_similar_but_distinct_drives_are_not_merged():
    tracker = gps_trip("t1", SOURCE_TELTONIKA, "2026-03-02T08:00:00", minutes=30, distance_m=12000)

    # Same vehicle, same length, two hours later — a separate lesson.
    later = gps_trip("r1", SOURCE_RUHAVIK, "2026-03-02T10:00:00", minutes=30, distance_m=12000)
    assert looks_like_same_drive(later, tracker) is False

    # Same start time, very different distance — not the same drive.
    longer = gps_trip("r2", SOURCE_RUHAVIK, "2026-03-02T08:00:00", minutes=30, distance_m=40000)
    assert looks_like_same_drive(longer, tracker) is False

    # Same time and distance but a different vehicle.
    other_vehicle = gps_trip("r3", SOURCE_RUHAVIK, "2026-03-02T08:00:00", distance_m=12000,
                             vehicle_id=VEHICLE_B)
    assert looks_like_same_drive(other_vehicle, tracker) is False

    # The genuine match: same vehicle, same window, comparable distance.
    same = gps_trip("r4", SOURCE_RUHAVIK, "2026-03-02T08:03:00", minutes=27, distance_m=12300)
    assert looks_like_same_drive(same, tracker) is True


# ── 11: origin is preserved ──

async def test_trip_source_is_preserved(mock_db):
    await mock_db.gps_trips.insert_many([
        gps_trip("t1", SOURCE_TELTONIKA, "2026-03-02T08:00:00"),
        gps_trip("r1", SOURCE_RUHAVIK, "2026-03-03T08:00:00", external_id="ruhavik:1"),
    ])

    by_id = {t["trip_id"]: t for t in await get_trips(mock_db)}

    assert by_id["t1"]["source"] == SOURCE_TELTONIKA
    assert by_id["r1"]["source"] == SOURCE_RUHAVIK
    assert by_id["r1"]["external_id"] == "ruhavik:1"


async def test_source_filter_selects_one_origin(mock_db):
    await mock_db.gps_trips.insert_many([
        gps_trip("t1", SOURCE_TELTONIKA, "2026-03-02T08:00:00"),
        gps_trip("r1", SOURCE_RUHAVIK, "2026-03-03T08:00:00", external_id="ruhavik:1"),
    ])

    only_ruhavik = await get_trips(mock_db, sources=[SOURCE_RUHAVIK])
    assert [t["trip_id"] for t in only_ruhavik] == ["r1"]

    only_tracker = await get_trips(mock_db, sources=[SOURCE_TELTONIKA])
    assert [t["trip_id"] for t in only_tracker] == ["t1"]


# ── double counting and demo data ──

async def test_logbook_projection_of_gps_trip_is_not_counted_twice(mock_db):
    """Syncing a GPS trip into the logbook must not double the kilometres."""
    await mock_db.gps_trips.insert_one(
        gps_trip("t1", SOURCE_TELTONIKA, "2026-03-02T08:00:00", distance_m=12000,
                 synced_to_logbook=True)
    )
    await mock_db.logbook.insert_one(
        logbook_entry("l1", "2026-03-02", distance_km=12, gps_source=True)
    )

    summary = summarize(await get_trips(mock_db))

    assert summary["total_trips"] == 1
    assert summary["total_distance_km"] == 12.0


async def test_mock_data_is_excluded_by_default(mock_db):
    await mock_db.gps_trips.insert_many([
        gps_trip("t1", SOURCE_TELTONIKA, "2026-03-02T08:00:00", distance_m=12000),
        gps_trip("m1", SOURCE_MOCK, "2026-03-02T12:00:00", distance_m=99000),
    ])

    summary = summarize(await get_trips(mock_db))
    assert summary["total_trips"] == 1
    assert summary["total_distance_km"] == 12.0

    with_mock = await get_trips(mock_db, sources=trips_service.ALL_SOURCES)
    assert len(with_mock) == 2


async def test_legacy_trips_without_source_are_still_reported(mock_db):
    """A database written before `source` existed must not lose its history."""
    legacy = gps_trip("legacy", SOURCE_TELTONIKA, "2026-03-02T08:00:00")
    legacy.pop("source")
    legacy.pop("duplicate_of")
    await mock_db.gps_trips.insert_one(legacy)

    result = await get_trips(mock_db)

    assert len(result) == 1
    assert result[0]["source"] == trips_service.LEGACY_SOURCE


# ── per-vehicle / per-instructor breakdowns ──

async def test_vehicle_and_instructor_breakdown_covers_every_source(mock_db):
    await mock_db.vehicles.insert_one({
        "vehicle_id": VEHICLE_A, "brand": "Škoda", "model": "Fabia",
        "registration_plate": "1AB 2345", "assigned_instructor_id": "inst_1",
    })
    await mock_db.instructors.insert_one({"instructor_id": "inst_1", "name": "Jan Novák"})
    await mock_db.gps_trips.insert_many([
        gps_trip("t1", SOURCE_TELTONIKA, "2026-03-02T08:00:00", distance_m=12000),
        gps_trip("r1", SOURCE_RUHAVIK, "2026-03-03T08:00:00", distance_m=8000,
                 external_id="ruhavik:1"),
    ])

    result = await get_trips(mock_db)
    await trips_service.resolve_trip_instructors(mock_db, result)
    summary = summarize(result)

    assert summary["by_vehicle"][0]["vehicle_id"] == VEHICLE_A
    assert summary["by_vehicle"][0]["distance_km"] == 20.0
    assert summary["by_vehicle"][0]["sources"] == {SOURCE_TELTONIKA: 1, SOURCE_RUHAVIK: 1}

    # GPS drives carry no instructor of their own; attribution goes through the
    # vehicle so instructor statistics are not limited to manual entries.
    assert summary["by_instructor"][0]["instructor_id"] == "inst_1"
    assert summary["by_instructor"][0]["instructor_name"] == "Jan Novák"
    assert summary["by_instructor"][0]["trips"] == 2


async def test_daily_breakdown_uses_local_dates(mock_db):
    """22:30 UTC in summer is 00:30 the next day in Prague."""
    await mock_db.gps_trips.insert_one(
        gps_trip("t_late", SOURCE_TELTONIKA, "2026-07-10T22:30:00", minutes=20, distance_m=5000)
    )

    result = await get_trips(mock_db)

    assert result[0]["date"] == "2026-07-11"
