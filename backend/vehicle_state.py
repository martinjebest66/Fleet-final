"""Odometer and fuel-level history of a vehicle.

Answers "what was the odometer and the fuel level of this car on that date?"

The readings are not stored a second time — they already exist across the
collections the application writes anyway, each with a different reliability:

  * ``vehicle_positions`` — the tracker reports its own accumulated distance
    (AVL IO 16) and, on an OBD-equipped install, the fuel level (IO 48 / 390).
    Dense, but the device odometer is *not* the dashboard reading.
  * ``fuel_entries``    — dashboard odometer written down at a refuelling.
  * ``qr_handovers`` / ``handover_protocols`` — dashboard odometer and a fuel
    gauge estimate from the handover form.
  * ``logbook``         — dashboard odometer at the end of a recorded drive.

Deriving from those keeps historical data usable straight away and means no
new write path can fall out of step with the source records.

The dashboard odometer for a moment in time is the last written-down reading
before it, plus the distance the tracker recorded since — reported explicitly
as an estimate, with the reading it was derived from.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from teltonika import (
    PARAM_FUEL_LEVEL_LITERS,
    PARAM_FUEL_LEVEL_PERCENT,
    PARAM_TRACKER_MILEAGE,
    PARAM_VEHICLE_MILEAGE,
)
from trips import REPORT_TZ, local_date_of, timestamp_range_query, to_utc

logger = logging.getLogger("fleet.vehicle_state")

# Where a reading came from, in decreasing trust for the dashboard odometer.
SOURCE_FUEL = "fuel"
SOURCE_HANDOVER = "handover"
SOURCE_LOGBOOK = "logbook"
SOURCE_GPS = "gps"
#: The vehicle's own odometer, read over CAN / OEM PIDs and reported by the
#: tracker as `can.vehicle.mileage`. Unlike the tracker's counted distance this
#: *is* the dashboard reading, so it needs no extrapolation.
SOURCE_CAN = "can"

SOURCE_LABELS = {
    SOURCE_FUEL: "Tankování",
    SOURCE_HANDOVER: "Předávací protokol",
    SOURCE_LOGBOOK: "Kniha jízd",
    SOURCE_GPS: "GPS tracker",
    SOURCE_CAN: "Tachometr vozidla (CAN)",
}

#: Readings whose odometer is the real vehicle odometer rather than an
#: accumulated distance. A CAN/OEM reading counts here: it comes off the same
#: instrument cluster a person would read.
DASHBOARD_SOURCES = (SOURCE_CAN, SOURCE_FUEL, SOURCE_HANDOVER, SOURCE_LOGBOOK)

#: Cap on GPS points scanned for one query, so a long period cannot pull the
#: whole position history into memory.
MAX_GPS_POINTS = 50000


def _combine_date_time(day: Any, clock: Optional[str]) -> Optional[datetime]:
    """Build a UTC instant from a YYYY-MM-DD date and an optional HH:MM."""
    if not day:
        return None
    text = str(day)[:10]
    time_part = (clock or "12:00").strip()
    if len(time_part) == 5 and ":" in time_part:
        time_part += ":00"
    elif not time_part:
        time_part = "12:00:00"
    try:
        naive = datetime.fromisoformat(f"{text}T{time_part}")
    except ValueError:
        return to_utc(text)
    # Dates typed by a person are local time.
    return naive.replace(tzinfo=REPORT_TZ).astimezone(timezone.utc)


def _reading(at: Optional[datetime], source: str, **fields) -> Optional[Dict[str, Any]]:
    if at is None:
        return None
    reading = {
        "at": at,
        "date": local_date_of(at),
        "time": at.astimezone(REPORT_TZ).strftime("%H:%M"),
        "source": source,
        "source_label": SOURCE_LABELS.get(source, source),
        "odometer_km": None,
        "fuel_level_percent": None,
        "fuel_level_liters": None,
        "gps_odometer_km": None,
        "note": None,
    }
    reading.update(fields)
    return reading


def _oem_mileage_km(obd: Dict[str, Any]) -> Optional[float]:
    """Real odometer from a legacy `obd` block (documents written before the
    canonical `can` block existed)."""
    for key, scale in (("oem_total_mileage", 1.0), ("can_total_mileage", 0.001)):
        value = obd.get(key)
        if value:
            try:
                return float(value) * scale
            except (TypeError, ValueError):
                continue
    return None


def _fuel_percent(can: Dict[str, Any], obd: Dict[str, Any]) -> Optional[int]:
    """Fuel level as a percentage, from whichever source reports one.

    A level reported in litres is deliberately *not* converted: without the
    tank size that would be a guess, and the earlier code showed the raw litre
    value as a percentage.
    """
    value = can.get(PARAM_FUEL_LEVEL_PERCENT)
    if value is None:
        value = obd.get("fuel_level")
    if value is None:
        value = obd.get("can_fuel_level")
    percent = _as_int(value)
    if percent is None or not (0 <= percent <= 100):
        return None
    return percent


def _fuel_liters(can: Dict[str, Any], obd: Dict[str, Any]) -> Optional[float]:
    value = can.get(PARAM_FUEL_LEVEL_LITERS)
    if value is None:
        raw = obd.get("oem_fuel_level")
        value = float(raw) * 0.1 if raw not in (None, "") else None
    try:
        return round(float(value), 1) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


async def collect_readings(
    db,
    vehicle_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_gps: bool = True,
    gps_limit: int = MAX_GPS_POINTS,
) -> List[Dict[str, Any]]:
    """Gather every odometer/fuel reading for a vehicle, oldest first."""
    lo = to_utc(f"{date_from}T00:00:00") - timedelta(days=1) if date_from else None
    hi = to_utc(f"{date_to}T23:59:59") + timedelta(days=1) if date_to else None

    readings: List[Dict[str, Any]] = []

    # --- refuelling ---
    fuel_query: Dict[str, Any] = {"vehicle_id": vehicle_id}
    if date_from or date_to:
        bounds = {}
        if date_from:
            bounds["$gte"] = str(date_from)[:10]
        if date_to:
            bounds["$lte"] = str(date_to)[:10]
        fuel_query["date"] = bounds
    for doc in await db.fuel_entries.find(fuel_query, {"_id": 0}).to_list(5000):
        entry = _reading(
            _combine_date_time(doc.get("date"), None),
            SOURCE_FUEL,
            odometer_km=_as_int(doc.get("odometer")),
            note=f"{doc.get('liters', 0)} l za {doc.get('total_price', 0)} Kč",
            liters=doc.get("liters"),
            total_price=doc.get("total_price"),
            record_id=doc.get("fuel_id"),
        )
        if entry:
            readings.append(entry)

    # --- handovers (both the QR form and the desktop protocol) ---
    for collection, id_field in (("qr_handovers", "qr_handover_id"),
                                 ("handover_protocols", "handover_id")):
        query: Dict[str, Any] = {"vehicle_id": vehicle_id}
        range_filter = timestamp_range_query("created_at", lo, hi)
        if range_filter:
            query.update(range_filter)
        for doc in await db[collection].find(query, {"_id": 0}).to_list(5000):
            entry = _reading(
                to_utc(doc.get("created_at")),
                SOURCE_HANDOVER,
                odometer_km=_as_int(doc.get("odometer")),
                fuel_level_percent=_as_int(doc.get("fuel_level")),
                note=doc.get("handler_name") or doc.get("type") or "předávka",
                record_id=doc.get(id_field),
            )
            if entry:
                readings.append(entry)

    # --- logbook ---
    log_query: Dict[str, Any] = {"vehicle_id": vehicle_id}
    if date_from or date_to:
        bounds = {}
        if date_from:
            bounds["$gte"] = str(date_from)[:10]
        if date_to:
            bounds["$lte"] = str(date_to)[:10]
        log_query["date"] = bounds
    for doc in await db.logbook.find(log_query, {"_id": 0}).to_list(5000):
        entry = _reading(
            _combine_date_time(doc.get("date"), doc.get("end_time")),
            SOURCE_LOGBOOK,
            odometer_km=_as_int(doc.get("end_odometer")),
            note=doc.get("route_description") or doc.get("purpose"),
            record_id=doc.get("entry_id"),
        )
        if entry:
            readings.append(entry)

    # --- tracker ---
    if include_gps:
        gps_query: Dict[str, Any] = {
            "vehicle_id": vehicle_id,
            "$or": [{"obd": {"$exists": True}}, {"can": {"$exists": True}}],
        }
        range_filter = timestamp_range_query("timestamp", lo, hi)
        if range_filter:
            # Two $or clauses cannot coexist at the top level.
            gps_query = {"$and": [gps_query, range_filter]}
        cursor = db.vehicle_positions.find(
            gps_query, {"_id": 0, "timestamp": 1, "obd": 1, "can": 1}
        ).sort("timestamp", 1)
        for doc in await cursor.to_list(gps_limit):
            obd = doc.get("obd") or {}
            can = doc.get("can") or {}
            at = to_utc(doc.get("timestamp"))

            # The real odometer, when the vehicle reports one, is a reading in
            # its own right — not something to extrapolate from.
            vehicle_km = can.get(PARAM_VEHICLE_MILEAGE)
            if vehicle_km is None:
                vehicle_km = _oem_mileage_km(obd)
            if vehicle_km:
                entry = _reading(
                    at, SOURCE_CAN,
                    odometer_km=_as_int(vehicle_km),
                    fuel_level_percent=_fuel_percent(can, obd),
                    fuel_level_liters=_fuel_liters(can, obd),
                    note="odečet z palubní jednotky vozidla",
                )
                if entry:
                    readings.append(entry)
                continue

            tracker_km = can.get(PARAM_TRACKER_MILEAGE)
            if tracker_km is None:
                total_m = _as_int(obd.get("total_odometer"))
                tracker_km = total_m / 1000.0 if total_m is not None else None
            fuel = _fuel_percent(can, obd)
            if tracker_km is None and fuel is None and _fuel_liters(can, obd) is None:
                continue
            entry = _reading(
                at, SOURCE_GPS,
                gps_odometer_km=round(tracker_km, 1) if tracker_km is not None else None,
                fuel_level_percent=fuel,
                fuel_level_liters=_fuel_liters(can, obd),
            )
            if entry:
                readings.append(entry)

    readings.sort(key=lambda r: r["at"])
    return readings


def _last_before(readings: List[Dict[str, Any]], at: datetime, predicate) -> Optional[Dict[str, Any]]:
    found = None
    for reading in readings:
        if reading["at"] > at:
            break
        if predicate(reading):
            found = reading
    return found


def _first_after(readings: List[Dict[str, Any]], at: datetime, predicate) -> Optional[Dict[str, Any]]:
    for reading in readings:
        if reading["at"] >= at and predicate(reading):
            return reading
    return None


def state_at(readings: List[Dict[str, Any]], at: datetime) -> Dict[str, Any]:
    """Odometer and fuel level in effect at `at`, with provenance.

    The odometer is the last written-down dashboard reading before `at`; when
    the tracker recorded further distance since then, that distance is added
    and the result is marked as an estimate rather than presented as if
    somebody had read it off the dashboard.
    """
    has_odo = lambda r: r["odometer_km"] is not None  # noqa: E731
    has_gps_odo = lambda r: r["gps_odometer_km"] is not None  # noqa: E731
    has_fuel = lambda r: r["fuel_level_percent"] is not None  # noqa: E731

    base = _last_before(readings, at, lambda r: has_odo(r) and r["source"] in DASHBOARD_SOURCES)
    gps_now = _last_before(readings, at, has_gps_odo)

    odometer_km = None
    delta_km = 0.0
    is_estimate = False
    source = None
    recorded_at = None

    if base:
        odometer_km = float(base["odometer_km"])
        source = base["source"]
        recorded_at = base["at"]
        gps_at_base = _first_after(readings, base["at"], has_gps_odo)
        if gps_now and gps_at_base and gps_now["at"] > base["at"]:
            delta_km = max(0.0, gps_now["gps_odometer_km"] - gps_at_base["gps_odometer_km"])
            if delta_km > 0:
                odometer_km += delta_km
                is_estimate = True

    fuel = _last_before(readings, at, has_fuel)
    fuel_liters = _last_before(readings, at, lambda r: r.get("fuel_level_liters") is not None)
    last_refuel = _last_before(readings, at, lambda r: r["source"] == SOURCE_FUEL)

    return {
        "at": at,
        "date": local_date_of(at),
        "odometer_km": round(odometer_km) if odometer_km is not None else None,
        "odometer_is_estimate": is_estimate,
        "odometer_gps_delta_km": round(delta_km, 1),
        "odometer_source": source,
        "odometer_source_label": SOURCE_LABELS.get(source) if source else None,
        "odometer_recorded_at": recorded_at,
        "fuel_level_percent": fuel["fuel_level_percent"] if fuel else None,
        "fuel_level_liters": fuel_liters["fuel_level_liters"] if fuel_liters else None,
        "fuel_source": fuel["source"] if fuel else None,
        "fuel_source_label": fuel["source_label"] if fuel else None,
        "fuel_recorded_at": fuel["at"] if fuel else None,
        "gps_odometer_km": gps_now["gps_odometer_km"] if gps_now else None,
        "last_refuel": {
            "at": last_refuel["at"],
            "date": last_refuel["date"],
            "odometer_km": last_refuel["odometer_km"],
            "liters": last_refuel.get("liters"),
            "total_price": last_refuel.get("total_price"),
        } if last_refuel else None,
    }


def daily_summary(readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per local day: closing odometer and fuel level.

    This is what the history view charts, so a month of tracker data becomes
    ~30 points instead of tens of thousands.

    The closing odometer uses the same rule as :func:`state_at` — the last
    written-down reading plus the distance the tracker recorded since — so the
    chart does not flatline between two refuellings while the car is being
    driven every day. Days resting on that extrapolation are flagged.
    """
    by_day: Dict[str, Dict[str, Any]] = {}

    # Running state, advanced in one forward pass over the readings.
    base_odo: Optional[float] = None        # last dashboard reading
    base_gps: Optional[float] = None        # tracker odometer at that moment
    current_gps: Optional[float] = None
    pending_base_gps = False                # base set, waiting for a GPS fix

    for reading in readings:
        day = reading["date"]
        if not day:
            continue
        bucket = by_day.setdefault(day, {
            "date": day, "odometer_km": None, "odometer_is_estimate": False,
            "odometer_from_reading": False,
            "fuel_level_percent": None, "fuel_level_liters": None, "gps_odometer_km": None,
            "readings": 0, "sources": set(),
        })
        bucket["readings"] += 1
        bucket["sources"].add(reading["source"])

        if reading["gps_odometer_km"] is not None:
            current_gps = reading["gps_odometer_km"]
            bucket["gps_odometer_km"] = current_gps
            if pending_base_gps:
                base_gps = current_gps
                pending_base_gps = False

        if reading["odometer_km"] is not None and reading["source"] in DASHBOARD_SOURCES:
            base_odo = float(reading["odometer_km"])
            base_gps = current_gps
            pending_base_gps = current_gps is None
            bucket["odometer_from_reading"] = True

        if reading["fuel_level_percent"] is not None:
            bucket["fuel_level_percent"] = reading["fuel_level_percent"]
        if reading.get("fuel_level_liters") is not None:
            bucket["fuel_level_liters"] = reading["fuel_level_liters"]

        if base_odo is not None:
            delta = 0.0
            if base_gps is not None and current_gps is not None:
                delta = max(0.0, current_gps - base_gps)
            bucket["odometer_km"] = round(base_odo + delta)
            bucket["odometer_is_estimate"] = delta > 0

    rows = []
    for day in sorted(by_day):
        bucket = by_day[day]
        bucket["sources"] = sorted(bucket["sources"])
        rows.append(bucket)

    # Carry the last known odometer forward so a quiet day is not a hole in
    # the chart. A day whose figure rests entirely on an earlier reading — no
    # dashboard reading of its own and no distance from the tracker — is
    # flagged, so the UI can show it as "unchanged" rather than as a fact.
    last_odo = None
    for row in rows:
        if row["odometer_km"] is None:
            row["odometer_km"] = last_odo
            row["odometer_carried_over"] = last_odo is not None
        else:
            row["odometer_carried_over"] = not (
                row.pop("odometer_from_reading", False) or row["odometer_is_estimate"]
            )
            last_odo = row["odometer_km"]
        row.pop("odometer_from_reading", None)
    return rows


def downsample(readings: List[Dict[str, Any]], max_points: int) -> List[Dict[str, Any]]:
    """Thin a reading list for display, always keeping non-GPS readings.

    Manual readings are few and each one matters; only the dense tracker
    stream is thinned. Nothing is deleted from storage.
    """
    if len(readings) <= max_points:
        return readings
    manual = [r for r in readings if r["source"] != SOURCE_GPS]
    gps = [r for r in readings if r["source"] == SOURCE_GPS]
    room = max(1, max_points - len(manual))
    if len(gps) > room:
        step = len(gps) / float(room)
        gps = [gps[int(i * step)] for i in range(room)] + [gps[-1]]
    merged = manual + gps
    merged.sort(key=lambda r: r["at"])
    return merged
