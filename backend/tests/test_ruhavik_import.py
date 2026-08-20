"""Ruhavik export parsing and idempotent import."""

from datetime import datetime, timedelta, timezone

import pytest

import ruhavik as ruhavik_import
from ruhavik import ImportError_, parse_ruhavik_file, store_trips
from trips import SOURCE_RUHAVIK, SOURCE_TELTONIKA, get_trips, summarize

VEHICLE = "veh_test"

GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Ruhavik</name><trkseg>
    <trkpt lat="50.0755" lon="14.4378"><time>2026-03-02T08:00:00Z</time><speed>10.0</speed></trkpt>
    <trkpt lat="50.0855" lon="14.4478"><time>2026-03-02T08:05:00Z</time><speed>15.0</speed></trkpt>
    <trkpt lat="50.0955" lon="14.4578"><time>2026-03-02T08:10:00Z</time><speed>12.0</speed></trkpt>
  </trkseg></trk>
  <trk><trkseg>
    <trkpt lat="50.1500" lon="14.5000"><time>2026-03-02T12:00:00Z</time><speed>8.0</speed></trkpt>
    <trkpt lat="50.1600" lon="14.5150"><time>2026-03-02T12:05:00Z</time><speed>18.0</speed></trkpt>
    <trkpt lat="50.1700" lon="14.5300"><time>2026-03-02T12:10:00Z</time><speed>20.0</speed></trkpt>
  </trkseg></trk>
</gpx>
"""

POINT_CSV = """timestamp,latitude,longitude,speed
2026-03-02T08:00:00Z,50.0755,14.4378,10
2026-03-02T08:05:00Z,50.0855,14.4478,30
2026-03-02T08:10:00Z,50.0955,14.4578,25
2026-03-02T14:00:00Z,50.2000,14.6000,40
2026-03-02T14:10:00Z,50.2300,14.6400,55
"""

TRIP_CSV = """id,start time,end time,distance,max speed,avg speed
trip-1,2026-03-02 08:00:00,2026-03-02 08:30:00,12.4,84,38
trip-2,2026-03-02 14:00:00,2026-03-02 14:45:00,25.0,101,42
"""


# ── parsing ─────────────────────────────────────────────────────

def test_gpx_split_into_trips_on_time_gaps():
    trips, errors, fmt = parse_ruhavik_file("export.gpx", GPX, VEHICLE)

    assert fmt == "gpx"
    assert errors == []
    # Two segments separated by ~4 hours become two drives.
    assert len(trips) == 2
    assert all(t["source"] == SOURCE_RUHAVIK for t in trips)
    assert all(t["distance"] > 0 for t in trips)
    assert all(t["external_id"] for t in trips)


def test_point_csv_split_into_trips():
    trips, errors, fmt = parse_ruhavik_file("points.csv", POINT_CSV, VEHICLE)

    assert fmt == "csv-points"
    assert len(trips) == 2
    assert trips[0]["route_points"]


def test_trip_level_csv_uses_provided_ids():
    trips, errors, fmt = parse_ruhavik_file("trips.csv", TRIP_CSV, VEHICLE)

    assert fmt == "csv-trips"
    assert len(trips) == 2
    assert trips[0]["distance"] == 12400
    assert trips[0]["max_speed"] == 84
    # The export's own trip id makes the import stable across re-uploads.
    assert trips[0]["external_id"] == "ruhavik:trip-1"
    assert trips[1]["external_id"] == "ruhavik:trip-2"


def test_unsupported_format_is_rejected():
    with pytest.raises(ImportError_):
        parse_ruhavik_file("notes.txt", "just some prose without any separators", VEHICLE)


def test_broken_gpx_is_rejected_with_a_message():
    with pytest.raises(ImportError_):
        parse_ruhavik_file("broken.gpx", "<?xml version='1.0'?><gpx><trk>", VEHICLE)


# ── 12: one bad record must not lose the rest ───────────────────

def test_invalid_rows_do_not_abort_the_import():
    csv = (
        "id,start time,end time,distance\n"
        "ok-1,2026-03-02 08:00:00,2026-03-02 08:30:00,12.4\n"
        "bad-1,,2026-03-02 09:30:00,5.0\n"                       # no start time
        "bad-2,not-a-date,2026-03-02 10:30:00,5.0\n"             # unparsable
        "bad-3,2026-03-02 12:00:00,2026-03-02 11:00:00,5.0\n"    # ends before it starts
        "ok-2,2026-03-02 14:00:00,2026-03-02 14:45:00,25.0\n"
    )
    trips, errors, _ = parse_ruhavik_file("mixed.csv", csv, VEHICLE)

    assert [t["external_id"] for t in trips] == ["ruhavik:ok-1", "ruhavik:ok-2"]
    assert len(errors) == 3
    assert all("řádek" in e for e in errors)  # every error names its source line


def test_points_without_coordinates_are_reported_not_fatal():
    csv = (
        "timestamp,latitude,longitude,speed\n"
        "2026-03-02T08:00:00Z,50.0755,14.4378,10\n"
        "2026-03-02T08:02:00Z,,,\n"
        "2026-03-02T08:04:00Z,0,0,0\n"      # 'no fix' position
        "2026-03-02T08:06:00Z,50.0955,14.4578,25\n"
    )
    trips, errors, _ = parse_ruhavik_file("gappy.csv", csv, VEHICLE)

    assert len(trips) == 1
    assert len(errors) == 2


def test_points_without_timestamps_are_skipped_individually():
    csv = (
        "timestamp,latitude,longitude\n"
        "2026-03-02T08:00:00Z,50.0755,14.4378\n"
        ",50.0800,14.4400\n"
        "2026-03-02T08:06:00Z,50.0955,14.4578\n"
    )
    trips, errors, _ = parse_ruhavik_file("notime.csv", csv, VEHICLE)

    assert len(trips) == 1
    assert any("razítk" in e for e in errors)


# ── 8: importing the same export twice creates no duplicates ────

async def test_importing_the_same_file_twice_is_idempotent(mock_db):
    trips, _, _ = parse_ruhavik_file("trips.csv", TRIP_CSV, VEHICLE)

    first = await store_trips(mock_db, trips)
    assert first["imported"] == 2
    assert first["skipped_already_imported"] == 0

    # Parse again — a fresh upload of the same export produces fresh trip_ids
    # but the same external ids.
    trips_again, _, _ = parse_ruhavik_file("trips.csv", TRIP_CSV, VEHICLE)
    second = await store_trips(mock_db, trips_again)

    assert second["imported"] == 0
    assert second["skipped_already_imported"] == 2
    assert await mock_db.gps_trips.count_documents({}) == 2

    summary = summarize(await get_trips(mock_db))
    assert summary["total_trips"] == 2
    assert summary["total_distance_km"] == pytest.approx(37.4)


async def test_repeated_gpx_import_without_export_ids_is_also_idempotent(mock_db):
    """Without a Ruhavik id the external id is derived from the drive itself."""
    trips, _, _ = parse_ruhavik_file("export.gpx", GPX, VEHICLE)
    await store_trips(mock_db, trips)

    trips_again, _, _ = parse_ruhavik_file("export.gpx", GPX, VEHICLE)
    second = await store_trips(mock_db, trips_again)

    assert second["imported"] == 0
    assert second["skipped_already_imported"] == len(trips)


async def test_duplicate_rows_inside_one_file_are_collapsed(mock_db):
    csv = TRIP_CSV + "trip-1,2026-03-02 08:00:00,2026-03-02 08:30:00,12.4,84,38\n"
    trips, _, _ = parse_ruhavik_file("dupes.csv", csv, VEHICLE)

    result = await store_trips(mock_db, trips)

    assert result["imported"] == 2
    assert result["skipped_already_imported"] == 1


# ── tracker/Ruhavik overlap ─────────────────────────────────────

async def test_drive_already_recorded_by_tracker_is_flagged_not_double_counted(mock_db):
    start = datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc)
    await mock_db.gps_trips.insert_one({
        "trip_id": "tracker-1",
        "vehicle_id": VEHICLE,
        "source": SOURCE_TELTONIKA,
        "start_time": start.replace(tzinfo=None).isoformat(),
        "end_time": (start + timedelta(minutes=30)).replace(tzinfo=None).isoformat(),
        "start_location": {}, "end_location": {}, "route_points": [],
        "distance": 12400, "max_speed": 84, "avg_speed": 38,
        "synced_to_logbook": False, "duplicate_of": None,
        "created_at": start.isoformat(),
    })

    trips, _, _ = parse_ruhavik_file("trips.csv", TRIP_CSV, VEHICLE)
    result = await store_trips(mock_db, trips)

    assert result["duplicates_of_tracker"] == 1
    assert result["imported"] == 1  # only the genuinely new second drive

    summary = summarize(await get_trips(mock_db))
    assert summary["total_trips"] == 2          # tracker drive + the new one
    assert summary["total_distance_km"] == pytest.approx(12.4 + 25.0)

    # The imported record still exists, with its origin intact.
    flagged = await mock_db.gps_trips.find_one({"duplicate_of": "tracker-1"}, {"_id": 0})
    assert flagged["source"] == SOURCE_RUHAVIK
    assert flagged["external_id"] == "ruhavik:trip-1"


async def test_a_separate_drive_at_a_different_time_is_not_flagged(mock_db):
    """A tracker drive earlier the same day must not swallow a later import."""
    start = datetime(2026, 3, 2, 5, 0, tzinfo=timezone.utc)
    await mock_db.gps_trips.insert_one({
        "trip_id": "tracker-early",
        "vehicle_id": VEHICLE,
        "source": SOURCE_TELTONIKA,
        "start_time": start.replace(tzinfo=None).isoformat(),
        "end_time": (start + timedelta(minutes=30)).replace(tzinfo=None).isoformat(),
        "start_location": {}, "end_location": {}, "route_points": [],
        "distance": 12400, "max_speed": 84, "avg_speed": 38,
        "synced_to_logbook": False, "duplicate_of": None,
        "created_at": start.isoformat(),
    })

    trips, _, _ = parse_ruhavik_file("trips.csv", TRIP_CSV, VEHICLE)
    result = await store_trips(mock_db, trips)

    assert result["duplicates_of_tracker"] == 0
    assert result["imported"] == 2
    assert summarize(await get_trips(mock_db))["total_trips"] == 3


# ── helpers ─────────────────────────────────────────────────────

def test_distance_estimate_is_realistic():
    """Prague to Brno is roughly 185 km as the crow flies."""
    metres = ruhavik_import.haversine_m(50.0755, 14.4378, 49.1951, 16.6068)
    assert 180_000 < metres < 190_000


def test_external_id_is_stable_and_specific():
    from trips import make_external_id

    a = make_external_id(SOURCE_RUHAVIK, VEHICLE, "2026-03-02T08:00:00", "2026-03-02T08:30:00", 12400)
    b = make_external_id(SOURCE_RUHAVIK, VEHICLE, "2026-03-02T08:00:00", "2026-03-02T08:30:00", 12400)
    c = make_external_id(SOURCE_RUHAVIK, VEHICLE, "2026-03-02T09:00:00", "2026-03-02T09:30:00", 12400)

    assert a == b
    assert a != c


def test_a_long_pause_inside_a_track_starts_a_new_drive():
    """Two hours of standing still is two drives, not one."""
    gpx = """<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
  <trkpt lat="50.0755" lon="14.4378"><time>2026-03-02T08:00:00Z</time></trkpt>
  <trkpt lat="50.0955" lon="14.4578"><time>2026-03-02T08:05:00Z</time></trkpt>
  <trkpt lat="50.2000" lon="14.6000"><time>2026-03-02T10:00:00Z</time></trkpt>
  <trkpt lat="50.2200" lon="14.6300"><time>2026-03-02T10:05:00Z</time></trkpt>
</trkseg></trk></gpx>"""
    trips, _, _ = parse_ruhavik_file("pause.gpx", gpx, VEHICLE)
    assert len(trips) == 2


def test_gps_drift_while_parked_is_not_reported_as_a_drive():
    """A stationary vehicle jitters by metres; that is not a trip."""
    gpx = """<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
  <trkpt lat="50.075500" lon="14.437800"><time>2026-03-02T08:00:00Z</time></trkpt>
  <trkpt lat="50.075510" lon="14.437810"><time>2026-03-02T08:01:00Z</time></trkpt>
  <trkpt lat="50.075495" lon="14.437795"><time>2026-03-02T08:02:00Z</time></trkpt>
</trkseg></trk></gpx>"""
    trips, _, _ = parse_ruhavik_file("parked.gpx", gpx, VEHICLE)
    assert trips == []
