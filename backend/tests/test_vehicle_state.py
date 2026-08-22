"""Odometer and fuel-level history: what did the car show on a given date?"""

from datetime import datetime, timedelta, timezone


import vehicle_state
from vehicle_state import (
    SOURCE_FUEL,
    SOURCE_GPS,
    SOURCE_HANDOVER,
    SOURCE_LOGBOOK,
    collect_readings,
    daily_summary,
    downsample,
    state_at,
)

VEHICLE = "veh_1"


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


async def seed(db, *, positions=(), fuel=(), handovers=(), logbook=()):
    if positions:
        await db.vehicle_positions.insert_many(list(positions))
    if fuel:
        await db.fuel_entries.insert_many(list(fuel))
    if handovers:
        await db.qr_handovers.insert_many(list(handovers))
    if logbook:
        await db.logbook.insert_many(list(logbook))


def gps_point(ts: str, total_odometer_m=None, fuel_percent=None, vehicle_id=VEHICLE):
    obd = {}
    if total_odometer_m is not None:
        obd["total_odometer"] = total_odometer_m
    if fuel_percent is not None:
        obd["fuel_level"] = fuel_percent
    return {
        "vehicle_id": vehicle_id, "lat": 50.0, "lng": 14.0, "speed": 40,
        "timestamp": utc(ts).isoformat(), "source": "teltonika", "obd": obd,
    }


def refuel(date: str, odometer: int, liters=40.0, price=1500.0, vehicle_id=VEHICLE):
    return {
        "fuel_id": f"fuel_{date}", "vehicle_id": vehicle_id, "date": date,
        "odometer": odometer, "liters": liters, "price_per_liter": 37.5,
        "total_price": price, "created_at": f"{date}T12:00:00",
    }


# ── collecting readings ─────────────────────────────────────────

async def test_readings_are_collected_from_every_source(mock_db):
    await seed(
        mock_db,
        positions=[gps_point("2026-03-02T08:00:00", 100_000, 80)],
        fuel=[refuel("2026-03-01", 41000)],
        handovers=[{"qr_handover_id": "qrh_1", "vehicle_id": VEHICLE, "odometer": 41200,
                    "fuel_level": 55, "handler_name": "Novák",
                    "created_at": "2026-03-03T07:00:00"}],
        logbook=[{"entry_id": "log_1", "vehicle_id": VEHICLE, "date": "2026-03-04",
                  "start_time": "08:00", "end_time": "09:30", "end_odometer": 41260,
                  "purpose": "výcvik", "created_at": "2026-03-04T09:30:00"}],
    )

    readings = await collect_readings(mock_db, VEHICLE)

    assert {r["source"] for r in readings} == {SOURCE_FUEL, SOURCE_GPS, SOURCE_HANDOVER, SOURCE_LOGBOOK}
    # Chronological, oldest first.
    assert [r["at"] for r in readings] == sorted(r["at"] for r in readings)


async def test_readings_of_other_vehicles_are_not_mixed_in(mock_db):
    await seed(
        mock_db,
        positions=[gps_point("2026-03-02T08:00:00", 100_000, 80, vehicle_id="veh_other")],
        fuel=[refuel("2026-03-01", 41000), refuel("2026-03-01", 99000, vehicle_id="veh_other")],
    )

    readings = await collect_readings(mock_db, VEHICLE)

    assert len(readings) == 1
    assert readings[0]["odometer_km"] == 41000


async def test_gps_points_without_odometer_or_fuel_are_ignored(mock_db):
    await seed(mock_db, positions=[
        gps_point("2026-03-02T08:00:00"),                       # no OBD values
        gps_point("2026-03-02T08:05:00", 100_000, None),
    ])

    readings = await collect_readings(mock_db, VEHICLE)

    assert len(readings) == 1
    assert readings[0]["gps_odometer_km"] == 100.0


# ── state at a point in time ────────────────────────────────────

async def test_state_uses_the_last_written_reading(mock_db):
    await seed(mock_db, fuel=[refuel("2026-03-01", 41000), refuel("2026-03-10", 41600)])
    readings = await collect_readings(mock_db, VEHICLE)

    state = state_at(readings, utc("2026-03-05T12:00:00"))

    assert state["odometer_km"] == 41000
    assert state["odometer_source"] == SOURCE_FUEL
    assert state["odometer_is_estimate"] is False


async def test_state_extrapolates_with_tracker_distance(mock_db):
    """Between two refuellings the odometer still moves; say so, and say it is an estimate."""
    await seed(
        mock_db,
        fuel=[refuel("2026-03-01", 41000)],
        positions=[
            gps_point("2026-03-01T12:30:00", 500_000, 90),   # tracker at the refuelling
            gps_point("2026-03-03T09:00:00", 542_000, 70),   # 42 km later
        ],
    )
    readings = await collect_readings(mock_db, VEHICLE)

    state = state_at(readings, utc("2026-03-03T10:00:00"))

    assert state["odometer_km"] == 41042
    assert state["odometer_is_estimate"] is True
    assert state["odometer_gps_delta_km"] == 42.0
    assert state["odometer_source"] == SOURCE_FUEL


async def test_a_later_written_reading_replaces_the_estimate(mock_db):
    await seed(
        mock_db,
        fuel=[refuel("2026-03-01", 41000)],
        positions=[
            gps_point("2026-03-01T12:30:00", 500_000),
            gps_point("2026-03-03T09:00:00", 542_000),
        ],
        handovers=[{"qr_handover_id": "qrh_1", "vehicle_id": VEHICLE, "odometer": 41050,
                    "fuel_level": 40, "created_at": "2026-03-03T18:00:00"}],
    )
    readings = await collect_readings(mock_db, VEHICLE)

    state = state_at(readings, utc("2026-03-04T08:00:00"))

    assert state["odometer_km"] == 41050
    assert state["odometer_is_estimate"] is False
    assert state["odometer_source"] == SOURCE_HANDOVER


async def test_state_before_any_record_is_unknown_not_zero(mock_db):
    await seed(mock_db, fuel=[refuel("2026-03-10", 41000)])
    readings = await collect_readings(mock_db, VEHICLE)

    state = state_at(readings, utc("2026-03-01T00:00:00"))

    assert state["odometer_km"] is None
    assert state["fuel_level_percent"] is None
    assert state["last_refuel"] is None


async def test_fuel_level_comes_from_the_most_recent_source(mock_db):
    await seed(
        mock_db,
        handovers=[{"qr_handover_id": "qrh_1", "vehicle_id": VEHICLE, "odometer": 41000,
                    "fuel_level": 90, "created_at": "2026-03-02T06:00:00"}],
        positions=[gps_point("2026-03-02T15:00:00", 500_000, 46)],
    )
    readings = await collect_readings(mock_db, VEHICLE)

    morning = state_at(readings, utc("2026-03-02T07:00:00"))
    evening = state_at(readings, utc("2026-03-02T20:00:00"))

    assert (morning["fuel_level_percent"], morning["fuel_source"]) == (90, SOURCE_HANDOVER)
    assert (evening["fuel_level_percent"], evening["fuel_source"]) == (46, SOURCE_GPS)


async def test_last_refuel_is_reported(mock_db):
    await seed(mock_db, fuel=[refuel("2026-03-01", 41000, liters=42.5, price=1600.0)])
    readings = await collect_readings(mock_db, VEHICLE)

    state = state_at(readings, utc("2026-03-05T00:00:00"))

    assert state["last_refuel"]["liters"] == 42.5
    assert state["last_refuel"]["total_price"] == 1600.0
    assert state["last_refuel"]["odometer_km"] == 41000


async def test_a_tracker_odometer_reset_does_not_produce_a_negative_delta(mock_db):
    """A replaced or reset tracker restarts its counter; never subtract km."""
    await seed(
        mock_db,
        fuel=[refuel("2026-03-01", 41000)],
        positions=[
            gps_point("2026-03-01T12:30:00", 900_000),
            gps_point("2026-03-05T09:00:00", 1_000),   # device replaced
        ],
    )
    readings = await collect_readings(mock_db, VEHICLE)

    state = state_at(readings, utc("2026-03-05T10:00:00"))

    assert state["odometer_km"] == 41000
    assert state["odometer_gps_delta_km"] == 0.0


# ── daily rollup ────────────────────────────────────────────────

async def test_daily_summary_has_one_row_per_day(mock_db):
    await seed(mock_db, positions=[
        gps_point("2026-03-02T08:00:00", 500_000, 80),
        gps_point("2026-03-02T18:00:00", 520_000, 60),
        gps_point("2026-03-03T09:00:00", 540_000, 50),
    ], fuel=[refuel("2026-03-02", 41000)])

    rows = daily_summary(await collect_readings(mock_db, VEHICLE))

    assert [r["date"] for r in rows] == ["2026-03-02", "2026-03-03"]
    assert rows[0]["fuel_level_percent"] == 60      # closing value of the day
    assert rows[1]["fuel_level_percent"] == 50


async def test_daily_odometer_follows_the_tracker_between_readings(mock_db):
    await seed(
        mock_db,
        fuel=[refuel("2026-03-01", 41000)],
        positions=[
            gps_point("2026-03-01T13:00:00", 500_000),
            gps_point("2026-03-02T18:00:00", 530_000),   # +30 km
            gps_point("2026-03-03T18:00:00", 555_000),   # +55 km total
        ],
    )

    rows = {r["date"]: r for r in daily_summary(await collect_readings(mock_db, VEHICLE))}

    assert rows["2026-03-01"]["odometer_km"] == 41000
    assert rows["2026-03-01"]["odometer_is_estimate"] is False
    assert rows["2026-03-02"]["odometer_km"] == 41030
    assert rows["2026-03-02"]["odometer_is_estimate"] is True
    assert rows["2026-03-03"]["odometer_km"] == 41055


def test_daily_summary_carries_a_quiet_day_forward():
    readings = [
        {"at": utc("2026-03-01T10:00:00"), "date": "2026-03-01", "source": SOURCE_FUEL,
         "odometer_km": 41000, "fuel_level_percent": None, "gps_odometer_km": None},
        {"at": utc("2026-03-02T10:00:00"), "date": "2026-03-02", "source": SOURCE_GPS,
         "odometer_km": None, "fuel_level_percent": 70, "gps_odometer_km": None},
    ]

    rows = daily_summary(readings)

    assert rows[1]["odometer_km"] == 41000
    assert rows[1]["odometer_carried_over"] is True


# ── display thinning ────────────────────────────────────────────

def test_downsampling_keeps_every_hand_written_reading():
    manual = [
        {"at": utc(f"2026-03-{d:02d}T10:00:00"), "date": f"2026-03-{d:02d}",
         "source": SOURCE_FUEL, "odometer_km": 41000 + d, "fuel_level_percent": None,
         "gps_odometer_km": None}
        for d in range(1, 6)
    ]
    gps = [
        {"at": utc("2026-03-01T10:00:00") + timedelta(minutes=i), "date": "2026-03-01",
         "source": SOURCE_GPS, "odometer_km": None, "fuel_level_percent": 50,
         "gps_odometer_km": 1000 + i}
        for i in range(2000)
    ]

    shown = downsample(sorted(manual + gps, key=lambda r: r["at"]), 100)

    assert len(shown) <= 102
    assert sum(1 for r in shown if r["source"] == SOURCE_FUEL) == 5
    assert shown == sorted(shown, key=lambda r: r["at"])


def test_downsampling_leaves_a_short_list_alone():
    readings = [
        {"at": utc("2026-03-01T10:00:00"), "date": "2026-03-01", "source": SOURCE_GPS,
         "odometer_km": None, "fuel_level_percent": 50, "gps_odometer_km": 10}
    ]
    assert downsample(readings, 100) == readings


def test_local_dates_are_used_for_grouping():
    """22:30 UTC in summer already belongs to the next Prague day."""
    reading = vehicle_state._reading(utc("2026-07-10T22:30:00"), SOURCE_GPS, gps_odometer_km=1.0)
    assert reading["date"] == "2026-07-11"
