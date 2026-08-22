"""Příjem pozic z trackeru a automatická tvorba jízd.

Obojí selhalo na reálném nasazení: pozice se zahazovaly kvůli nulovému počtu
družic a z uložených pozic se nikdy nestaly jízdy, protože detekce běžela jen
na kliknutí.
"""

from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

import server
from teltonika import build_avl_packet, parse_avl_packet

IMEI = "353742378891493"
VEHICLE = "veh_1"


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


@pytest.fixture
def db(monkeypatch):
    database = AsyncMongoMockClient()["fleet_gps_test"]
    monkeypatch.setattr(server, "db", database)
    return database


async def register(db):
    await db.gps_devices.insert_one(
        {"device_id": "dev_1", "imei": IMEI, "vehicle_id": VEHICLE}
    )


def records(*specs):
    """specs: (lat, lng, speed, satellites, ts_ms, ignition)"""
    return parse_avl_packet(build_avl_packet([
        {"lat": lat, "lng": lng, "speed": speed, "satellites": sats, "ts_ms": ts,
         "io": {239: (1, 1 if ign else 0)}}
        for lat, lng, speed, sats, ts, ign in specs
    ]))


# ── příjem pozic ────────────────────────────────────────────────

async def test_position_without_satellites_is_still_stored(db):
    """Záznam s platnými souřadnicemi a nulou družic je poslední známá pozice.

    Dřív se zahodil — a s ním i stav zapalování a tachometru.
    """
    await register(db)
    base = 1_772_000_000_000

    await server.on_teltonika_records(IMEI, records(
        (50.2306, 12.8720, 0, 0, base, True),
    ))

    stored = await db.vehicle_positions.find({}, {"_id": 0}).to_list(10)
    assert len(stored) == 1
    assert stored[0]["gps_fix"] is False       # označeno, ale uloženo
    assert stored[0]["lat"] == pytest.approx(50.2306, abs=1e-5)


async def test_position_without_a_fix_is_still_rejected(db):
    """Nulové souřadnice jsou skutečné 'bez fixu' a uložit se nesmí."""
    await register(db)
    base = 1_772_000_000_000

    await server.on_teltonika_records(IMEI, records(
        (0.0, 0.0, 0, 0, base, False),
        (50.2306, 12.8720, 30, 9, base + 60_000, True),
    ))

    stored = await db.vehicle_positions.find({}, {"_id": 0}).to_list(10)
    assert len(stored) == 1
    assert stored[0]["gps_fix"] is True


async def test_a_real_fix_is_marked_as_such(db):
    await register(db)
    await server.on_teltonika_records(IMEI, records(
        (50.2306, 12.8720, 45, 9, 1_772_000_000_000, True),
    ))

    stored = await db.vehicle_positions.find_one({}, {"_id": 0})
    assert stored["gps_fix"] is True
    assert stored["satellites"] == 9


# ── automatická detekce jízd ────────────────────────────────────

async def positions(db, start: str, count: int, *, ignition=True, step_min=1,
                    lat0=50.2306, lng0=12.8720, vehicle_id=VEHICLE):
    at = utc(start)
    docs = []
    for i in range(count):
        docs.append({
            "vehicle_id": vehicle_id,
            "lat": lat0 + i * 0.004, "lng": lng0 + i * 0.005,
            "speed": 45 if ignition else 0,
            "ignition": ignition,
            "timestamp": (at + timedelta(minutes=i * step_min)).isoformat(),
        })
    await db.vehicle_positions.insert_many(docs)


async def test_positions_become_a_trip(db):
    await positions(db, "2026-08-20T08:00:00", 8)
    await positions(db, "2026-08-20T08:10:00", 1, ignition=False)

    result = await server._detect_trips_for_vehicle(VEHICLE)

    assert result["trips"] == 1
    trip = await db.gps_trips.find_one({}, {"_id": 0})
    assert trip["source"] == "teltonika"
    assert trip["distance"] > 100


async def test_running_detection_again_does_not_duplicate(db):
    await positions(db, "2026-08-20T08:00:00", 8)
    await positions(db, "2026-08-20T08:10:00", 1, ignition=False)

    first = await server._detect_trips_for_vehicle(VEHICLE)
    second = await server._detect_trips_for_vehicle(VEHICLE)

    assert first["trips"] == 1
    assert second["trips"] == 0
    assert second["skipped_existing"] == 1
    assert await db.gps_trips.count_documents({}) == 1


async def test_a_long_gap_splits_two_drives(db):
    """Tracker často neodešle poslední záznam s vypnutým zapalováním."""
    await positions(db, "2026-08-20T08:00:00", 6)
    await positions(db, "2026-08-20T14:00:00", 6, lat0=50.30, lng0=12.95)

    result = await server._detect_trips_for_vehicle(VEHICLE)

    assert result["trips"] == 2


async def test_a_parked_vehicle_produces_no_trip(db):
    await positions(db, "2026-08-20T08:00:00", 10, ignition=False)

    result = await server._detect_trips_for_vehicle(VEHICLE)

    assert result["trips"] == 0


async def test_gps_drift_while_parked_is_not_a_trip(db):
    """Zapalování zapnuté, ale vozidlo stojí — pod 100 m se jízda nezaloží."""
    at = utc("2026-08-20T08:00:00")
    await db.vehicle_positions.insert_many([
        {"vehicle_id": VEHICLE, "lat": 50.230500 + i * 0.000005,
         "lng": 12.872000, "speed": 0, "ignition": True,
         "timestamp": (at + timedelta(minutes=i)).isoformat()}
        for i in range(6)
    ])

    result = await server._detect_trips_for_vehicle(VEHICLE)

    assert result["trips"] == 0


async def test_detection_can_be_limited_to_recent_positions(db):
    """Plánovaný běh nesmí procházet celou historii pokaždé znovu."""
    await positions(db, "2026-01-01T08:00:00", 8)
    await positions(db, "2026-01-01T08:10:00", 1, ignition=False)
    await positions(db, "2026-08-20T08:00:00", 8)
    await positions(db, "2026-08-20T08:10:00", 1, ignition=False)

    recent = await server._detect_trips_for_vehicle(
        VEHICLE, since=utc("2026-08-01T00:00:00")
    )

    assert recent["trips"] == 1
    assert recent["positions"] == 9      # leden se vůbec nenačetl


async def test_trips_of_different_vehicles_stay_separate(db):
    await positions(db, "2026-08-20T08:00:00", 6)
    await positions(db, "2026-08-20T08:06:00", 1, ignition=False)
    await positions(db, "2026-08-20T08:00:00", 6, vehicle_id="veh_2",
                    lat0=49.0, lng0=14.0)
    await positions(db, "2026-08-20T08:06:00", 1, ignition=False, vehicle_id="veh_2")

    await server._detect_trips_for_vehicle(VEHICLE)
    await server._detect_trips_for_vehicle("veh_2")

    assert await db.gps_trips.count_documents({"vehicle_id": VEHICLE}) == 1
    assert await db.gps_trips.count_documents({"vehicle_id": "veh_2"}) == 1


async def test_the_whole_path_from_packet_to_trip(db):
    """Od AVL paketu k jízdě v reportu, bez jediného kliknutí."""
    from trips import get_trips, summarize

    await register(db)
    base = int(utc("2026-08-20T08:00:00").timestamp() * 1000)

    driving = [(50.2306 + i * 0.004, 12.8720 + i * 0.005, 50, 9,
                base + i * 60_000, True) for i in range(8)]
    parked = [(50.2306 + 8 * 0.004, 12.8720 + 8 * 0.005, 0, 9,
               base + 8 * 60_000, False)]
    await server.on_teltonika_records(IMEI, records(*driving, *parked))

    assert await db.vehicle_positions.count_documents({}) == 9

    await server._detect_trips_for_vehicle(VEHICLE)

    reported = await get_trips(db, date_from="2026-08-20", date_to="2026-08-20")
    summary = summarize(reported)
    assert summary["total_trips"] == 1
    assert summary["by_source"]["teltonika"]["trips"] == 1
    assert summary["total_distance_km"] > 0


async def test_a_drive_still_in_progress_is_not_closed_yet(db):
    """Vozidlo, které právě jede, nesmí dostat useknutou jízdu."""
    now = datetime.now(timezone.utc)
    await db.vehicle_positions.insert_many([
        {"vehicle_id": VEHICLE, "lat": 50.2306 + i * 0.004, "lng": 12.8720 + i * 0.005,
         "speed": 45, "ignition": True,
         "timestamp": (now - timedelta(minutes=6 - i)).isoformat()}
        for i in range(6)
    ])

    result = await server._detect_trips_for_vehicle(VEHICLE)

    assert result["trips"] == 0        # jízda pokračuje, uzavře ji další běh


async def test_an_abandoned_drive_is_closed_and_kept(db):
    """Tracker přestal hlásit uprostřed jízdy — o data se přijít nesmí."""
    await positions(db, "2026-08-20T08:00:00", 8)   # nikdy nepřijde ignition off

    result = await server._detect_trips_for_vehicle(VEHICLE)

    assert result["trips"] == 1
