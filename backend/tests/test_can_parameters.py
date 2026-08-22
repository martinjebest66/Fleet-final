"""Canonical vehicle parameters from Teltonika AVL IO elements.

Which numbered IO element carries the odometer depends on the tracker model
and on whether a CAN adapter is fitted, so the mapping is configurable and the
units are explicit. Getting a unit wrong here is a factor-of-1000 error in the
logbook, which is why every id in the default table has a documented unit.
"""

from datetime import datetime, timezone

from teltonika import (
    DEFAULT_PARAM_IO_MAP,
    PARAM_FUEL_LEVEL_LITERS,
    PARAM_FUEL_LEVEL_PERCENT,
    PARAM_TRACKER_MILEAGE,
    PARAM_VEHICLE_MILEAGE,
    build_param_io_map,
    extract_vehicle_parameters,
)
from vehicle_state import SOURCE_CAN, SOURCE_GPS, collect_readings, state_at

VEHICLE = "veh_1"


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


# ── extraction and units ────────────────────────────────────────

def test_oem_total_mileage_is_the_real_odometer_in_km():
    """AVL 389 (OBD OEM Total Mileage) is reported in kilometres."""
    params = extract_vehicle_parameters({389: 132_456})

    assert params[PARAM_VEHICLE_MILEAGE] == 132_456.0


def test_can_adapter_mileage_is_converted_from_metres():
    """AVL 87 (CAN adapter Total Mileage) is in metres, not kilometres."""
    params = extract_vehicle_parameters({87: 132_456_000})

    assert params[PARAM_VEHICLE_MILEAGE] == 132_456.0


def test_tracker_odometer_is_kept_apart_from_the_vehicle_odometer():
    """AVL 16 is distance the device counted, not the dashboard reading."""
    params = extract_vehicle_parameters({16: 8_500_000, 389: 132_456})

    assert params[PARAM_TRACKER_MILEAGE] == 8_500.0
    assert params[PARAM_VEHICLE_MILEAGE] == 132_456.0
    assert params[PARAM_TRACKER_MILEAGE] != params[PARAM_VEHICLE_MILEAGE]


def test_oem_fuel_level_is_litres_not_percent():
    """AVL 390 carries tenths of a litre; reading it as % was wrong."""
    params = extract_vehicle_parameters({390: 452})

    assert params[PARAM_FUEL_LEVEL_LITERS] == 45.2
    assert PARAM_FUEL_LEVEL_PERCENT not in params


def test_standard_obd_fuel_level_is_a_percentage():
    params = extract_vehicle_parameters({48: 62})

    assert params[PARAM_FUEL_LEVEL_PERCENT] == 62.0


def test_a_zero_odometer_means_not_read_yet():
    """A device that has not read the value yet reports 0."""
    params = extract_vehicle_parameters({389: 0, 48: 55})

    assert PARAM_VEHICLE_MILEAGE not in params
    assert params[PARAM_FUEL_LEVEL_PERCENT] == 55.0


def test_unknown_io_elements_are_ignored():
    assert extract_vehicle_parameters({9999: 1234}) == {}


def test_non_numeric_values_are_ignored():
    """Variable-length Codec 8E elements arrive as hex strings."""
    assert extract_vehicle_parameters({389: "00ff"}) == {}


# ── configurable mapping ────────────────────────────────────────

def test_an_extra_id_can_be_mapped_with_its_unit():
    mapping = build_param_io_map({PARAM_VEHICLE_MILEAGE: ["1176:km"]})

    assert extract_vehicle_parameters({1176: 90_000}, mapping)[PARAM_VEHICLE_MILEAGE] == 90_000.0


def test_an_extra_id_without_a_unit_is_refused_rather_than_guessed():
    """Assuming km for a metre value would inflate the odometer 1000-fold."""
    mapping = build_param_io_map({PARAM_VEHICLE_MILEAGE: ["1176"]})

    assert 1176 not in mapping
    assert extract_vehicle_parameters({1176: 90_000}, mapping) == {}


def test_a_known_id_may_be_remapped_to_another_parameter():
    """Some models use AVL 36 for mileage, others for engine RPM."""
    mapping = build_param_io_map({PARAM_VEHICLE_MILEAGE: ["36:km"]})

    assert extract_vehicle_parameters({36: 120_500}, mapping)[PARAM_VEHICLE_MILEAGE] == 120_500.0


def test_a_nonsense_configuration_entry_does_not_break_the_mapping():
    mapping = build_param_io_map({PARAM_VEHICLE_MILEAGE: ["", "abc", "389:parsecs", "87"]})

    assert mapping[87] == (PARAM_VEHICLE_MILEAGE, "m")
    assert mapping[389] == DEFAULT_PARAM_IO_MAP[389]


def test_every_default_id_has_a_known_unit():
    from teltonika import UNIT_SCALE

    for io_id, (param, unit) in DEFAULT_PARAM_IO_MAP.items():
        assert unit in UNIT_SCALE, f"AVL {io_id} ({param}) has unit {unit!r}"


# ── the odometer becomes a reading, not an estimate ─────────────

def can_position(ts: str, mileage_km=None, fuel_percent=None, fuel_liters=None):
    can = {}
    if mileage_km is not None:
        can[PARAM_VEHICLE_MILEAGE] = mileage_km
    if fuel_percent is not None:
        can[PARAM_FUEL_LEVEL_PERCENT] = fuel_percent
    if fuel_liters is not None:
        can[PARAM_FUEL_LEVEL_LITERS] = fuel_liters
    return {
        "vehicle_id": VEHICLE, "lat": 50.0, "lng": 14.0, "speed": 40,
        "timestamp": utc(ts).isoformat(), "source": "teltonika", "can": can,
    }


async def test_a_can_odometer_is_reported_as_a_reading(mock_db):
    await mock_db.vehicle_positions.insert_one(
        can_position("2026-03-02T08:00:00", mileage_km=132_456, fuel_percent=58)
    )

    readings = await collect_readings(mock_db, VEHICLE)
    state = state_at(readings, utc("2026-03-02T09:00:00"))

    assert state["odometer_km"] == 132_456
    assert state["odometer_is_estimate"] is False       # no extrapolation needed
    assert state["odometer_source"] == SOURCE_CAN
    assert state["fuel_level_percent"] == 58


async def test_the_can_odometer_wins_over_an_older_manual_reading(mock_db):
    await mock_db.fuel_entries.insert_one({
        "fuel_id": "fuel_1", "vehicle_id": VEHICLE, "date": "2026-03-01",
        "odometer": 132_000, "liters": 40.0, "total_price": 1500.0,
    })
    await mock_db.vehicle_positions.insert_one(
        can_position("2026-03-02T08:00:00", mileage_km=132_456)
    )

    state = state_at(await collect_readings(mock_db, VEHICLE), utc("2026-03-02T09:00:00"))

    assert state["odometer_km"] == 132_456
    assert state["odometer_source"] == SOURCE_CAN
    assert state["odometer_is_estimate"] is False


async def test_without_a_can_odometer_the_estimate_still_applies(mock_db):
    """Trackers that only count their own distance keep the old behaviour."""
    await mock_db.fuel_entries.insert_one({
        "fuel_id": "fuel_1", "vehicle_id": VEHICLE, "date": "2026-03-01",
        "odometer": 132_000, "liters": 40.0, "total_price": 1500.0,
    })
    await mock_db.vehicle_positions.insert_many([
        {"vehicle_id": VEHICLE, "lat": 50.0, "lng": 14.0, "speed": 40,
         "timestamp": utc("2026-03-01T13:00:00").isoformat(),
         "can": {PARAM_TRACKER_MILEAGE: 8_500.0}},
        {"vehicle_id": VEHICLE, "lat": 50.0, "lng": 14.0, "speed": 40,
         "timestamp": utc("2026-03-02T13:00:00").isoformat(),
         "can": {PARAM_TRACKER_MILEAGE: 8_530.0}},
    ])

    state = state_at(await collect_readings(mock_db, VEHICLE), utc("2026-03-02T14:00:00"))

    assert state["odometer_km"] == 132_030
    assert state["odometer_is_estimate"] is True
    assert state["odometer_source"] == "fuel"


async def test_fuel_in_litres_is_not_passed_off_as_a_percentage(mock_db):
    await mock_db.vehicle_positions.insert_one(
        can_position("2026-03-02T08:00:00", mileage_km=100_000, fuel_liters=45.2)
    )

    state = state_at(await collect_readings(mock_db, VEHICLE), utc("2026-03-02T09:00:00"))

    assert state["fuel_level_liters"] == 45.2
    assert state["fuel_level_percent"] is None


async def test_an_implausible_fuel_percentage_is_dropped(mock_db):
    """A litre value that reached a percent field would read like 452 %."""
    await mock_db.vehicle_positions.insert_one({
        "vehicle_id": VEHICLE, "lat": 50.0, "lng": 14.0, "speed": 0,
        "timestamp": utc("2026-03-02T08:00:00").isoformat(),
        "obd": {"fuel_level": 452, "total_odometer": 1_000_000},
    })

    state = state_at(await collect_readings(mock_db, VEHICLE), utc("2026-03-02T09:00:00"))

    assert state["fuel_level_percent"] is None


async def test_legacy_positions_written_before_the_can_block_still_work(mock_db):
    """Data already in the database has `obd`, not `can`."""
    await mock_db.vehicle_positions.insert_one({
        "vehicle_id": VEHICLE, "lat": 50.0, "lng": 14.0, "speed": 40,
        "timestamp": utc("2026-03-02T08:00:00").isoformat(),
        "obd": {"oem_total_mileage": 132_456, "fuel_level": 58},
    })

    state = state_at(await collect_readings(mock_db, VEHICLE), utc("2026-03-02T09:00:00"))

    assert state["odometer_km"] == 132_456
    assert state["odometer_source"] == SOURCE_CAN
    assert state["fuel_level_percent"] == 58


async def test_a_tracker_only_position_is_still_a_gps_reading(mock_db):
    await mock_db.vehicle_positions.insert_one({
        "vehicle_id": VEHICLE, "lat": 50.0, "lng": 14.0, "speed": 40,
        "timestamp": utc("2026-03-02T08:00:00").isoformat(),
        "obd": {"total_odometer": 8_500_000, "fuel_level": 60},
    })

    readings = await collect_readings(mock_db, VEHICLE)

    assert readings[0]["source"] == SOURCE_GPS
    assert readings[0]["gps_odometer_km"] == 8_500.0
    assert readings[0]["odometer_km"] is None
