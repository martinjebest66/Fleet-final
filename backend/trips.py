"""Unified trip model and reporting layer.

Every drive the system knows about — recorded by a Teltonika tracker, imported
from Ruhavik, or entered by hand in the logbook — is normalised into one shape
here. Reports then aggregate that single stream instead of each screen reaching
into a different collection with a different definition of "a trip".

Storage stays where it was (`gps_trips` for GPS-derived drives, `logbook` for
manual entries) so no data migration is required, but every trip carries an
explicit `source` so the origin is never lost and can still be filtered on.

Double counting is avoided in two places:
  * a logbook entry created by syncing a GPS trip (`gps_source: true`) is a
    projection of that trip, so the trip is counted and the projection is not;
  * an imported trip recognised as the same physical drive already recorded by
    a tracker is stored with `duplicate_of` set and excluded from reports.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date as date_cls, datetime, time as time_cls, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence
from zoneinfo import ZoneInfo

logger = logging.getLogger("fleet.trips")

REPORT_TZ = ZoneInfo("Europe/Prague")

SOURCE_TELTONIKA = "teltonika"
SOURCE_RUHAVIK = "ruhavik"
SOURCE_MANUAL = "manual"
SOURCE_MOCK = "mock"

#: Sources that represent a real vehicle movement and therefore belong in
#: reports. `mock` is generated demo data and is deliberately excluded.
REPORTABLE_SOURCES = (SOURCE_TELTONIKA, SOURCE_RUHAVIK, SOURCE_MANUAL)
ALL_SOURCES = REPORTABLE_SOURCES + (SOURCE_MOCK,)

#: Trips older than this are assumed to predate the `source` field and are
#: reported as Teltonika/GPS data, which is what they were.
LEGACY_SOURCE = SOURCE_TELTONIKA

# Duplicate detection thresholds. Deliberately conservative: a candidate must
# match a stored trip on the vehicle, on *both* endpoints in time, and on
# distance, before it is treated as the same physical drive.
DUP_TIME_TOLERANCE_MIN = 10
DUP_DISTANCE_TOLERANCE_RATIO = 0.25
DUP_DISTANCE_TOLERANCE_M = 1000


# ── datetime helpers ────────────────────────────────────────────

def to_utc(value: Any) -> Optional[datetime]:
    """Coerce a stored timestamp (ISO string or datetime) to aware UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    else:
        return None
    if dt.tzinfo is None:
        # Naive timestamps in this codebase are always UTC (they come from
        # datetime.now(timezone.utc).isoformat() or GPS records).
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def local_date_of(dt: Optional[datetime]) -> Optional[str]:
    """Local (Europe/Prague) calendar date of a UTC instant, as YYYY-MM-DD."""
    if dt is None:
        return None
    return dt.astimezone(REPORT_TZ).date().isoformat()


def _parse_iso_date(value: Optional[str]) -> Optional[date_cls]:
    if not value:
        return None
    try:
        return date_cls.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _window_bounds(date_from: Optional[str], date_to: Optional[str]):
    """UTC bounds covering the requested local-date window, widened by a day.

    The extra day absorbs the UTC/local offset; results are filtered exactly on
    the local date afterwards.
    """
    start_dt = end_dt = None
    d_from = _parse_iso_date(date_from)
    d_to = _parse_iso_date(date_to)
    if d_from:
        start_dt = datetime.combine(d_from - timedelta(days=1), time_cls.min, tzinfo=timezone.utc)
    if d_to:
        end_dt = datetime.combine(d_to + timedelta(days=1), time_cls.max, tzinfo=timezone.utc)
    return start_dt, end_dt


def timestamp_range_query(field: str, start_dt: Optional[datetime], end_dt: Optional[datetime]) -> Optional[dict]:
    """Range filter tolerating both ISO-string and BSON-date storage.

    Timestamps in this database are written as ISO strings in some places and
    as BSON dates in others, and a Mongo range query does not span BSON types.
    Matching either form keeps the query indexed while remaining correct
    whichever representation a document happens to use.
    """
    if start_dt is None and end_dt is None:
        return None
    as_str: Dict[str, Any] = {}
    as_dt: Dict[str, Any] = {}
    if start_dt is not None:
        as_str["$gte"] = start_dt.replace(tzinfo=None).isoformat()
        as_dt["$gte"] = start_dt
    if end_dt is not None:
        as_str["$lte"] = end_dt.replace(tzinfo=None).isoformat() + "￿"
        as_dt["$lte"] = end_dt
    return {"$or": [{field: as_str}, {field: as_dt}]}


_range_query = timestamp_range_query


# ── normalisation ───────────────────────────────────────────────

def trip_source(doc: Dict[str, Any]) -> str:
    """Source of a stored gps_trips document, with a legacy fallback."""
    source = (doc.get("source") or "").strip().lower()
    if source in ALL_SOURCES:
        return source
    if doc.get("mock") or doc.get("is_mock"):
        return SOURCE_MOCK
    return LEGACY_SOURCE


def normalize_gps_trip(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a `gps_trips` document into the unified trip shape."""
    start = to_utc(doc.get("start_time"))
    end = to_utc(doc.get("end_time"))
    distance_m = doc.get("distance") or 0
    try:
        distance_m = int(distance_m)
    except (TypeError, ValueError):
        distance_m = 0
    duration_min = int((end - start).total_seconds() / 60) if (start and end and end >= start) else 0
    start_loc = doc.get("start_location") or {}
    end_loc = doc.get("end_location") or {}
    return {
        "trip_id": doc.get("trip_id"),
        "source": trip_source(doc),
        "origin_collection": "gps_trips",
        "external_id": doc.get("external_id"),
        "vehicle_id": doc.get("vehicle_id"),
        "instructor_id": doc.get("instructor_id"),
        "start_time": start,
        "end_time": end,
        "date": local_date_of(start),
        "distance_m": distance_m,
        "distance_km": round(distance_m / 1000.0, 2),
        "duration_min": duration_min,
        "max_speed": doc.get("max_speed") or 0,
        "avg_speed": doc.get("avg_speed") or 0,
        "start_location": start_loc,
        "end_location": end_loc,
        "start_address": start_loc.get("address") or "",
        "end_address": end_loc.get("address") or "",
        "synced_to_logbook": bool(doc.get("synced_to_logbook")),
        "duplicate_of": doc.get("duplicate_of"),
        "route_point_count": len(doc.get("route_points") or []),
        "purpose": doc.get("purpose") or "výcvik",
        "notes": doc.get("notes"),
    }


def normalize_logbook_entry(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a manual `logbook` entry into the unified trip shape."""
    day = str(doc.get("date") or "")[:10]
    start = to_utc(f"{day}T{(doc.get('start_time') or '00:00')}:00") if day else None
    end = to_utc(f"{day}T{(doc.get('end_time') or '00:00')}:00") if day else None
    if start and end and end < start:  # crossed midnight
        end = end + timedelta(days=1)
    try:
        distance_km = float(doc.get("distance") or 0)
    except (TypeError, ValueError):
        distance_km = 0.0
    return {
        "trip_id": doc.get("entry_id"),
        "source": SOURCE_MANUAL,
        "origin_collection": "logbook",
        "external_id": None,
        "vehicle_id": doc.get("vehicle_id"),
        "instructor_id": doc.get("instructor_id"),
        "start_time": start,
        "end_time": end,
        "date": day or None,
        "distance_m": int(round(distance_km * 1000)),
        "distance_km": round(distance_km, 2),
        "duration_min": int((end - start).total_seconds() / 60) if (start and end) else 0,
        "max_speed": 0,
        "avg_speed": 0,
        "start_location": {},
        "end_location": {},
        "start_address": doc.get("start_location") or "",
        "end_address": doc.get("end_location") or "",
        "synced_to_logbook": True,
        "duplicate_of": None,
        "route_point_count": 0,
        "purpose": doc.get("purpose") or "",
        "notes": doc.get("notes"),
    }


# ── querying ────────────────────────────────────────────────────

async def get_trips(
    db,
    vehicle_id: Optional[str] = None,
    vehicle_ids: Optional[Sequence[str]] = None,
    instructor_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sources: Optional[Iterable[str]] = None,
    include_duplicates: bool = False,
    include_manual: bool = True,
    limit: int = 20000,
) -> List[Dict[str, Any]]:
    """Return every relevant trip, from every source, in one normalised list.

    This is the single entry point every report is expected to use.

    * `sources` — restrict to explicit sources; defaults to every source that
      represents a real drive (mock/demo data is never included by default).
    * `include_duplicates` — when False (default) trips flagged as a duplicate
      of an already-recorded drive are left out so distances are not counted
      twice.
    * `include_manual` — manual logbook entries. Logbook rows that are merely a
      projection of a GPS trip (`gps_source: true`) are always skipped; the
      underlying trip is authoritative.
    """
    wanted_sources = {s.strip().lower() for s in sources} if sources else set(REPORTABLE_SOURCES)
    start_dt, end_dt = _window_bounds(date_from, date_to)

    trips: List[Dict[str, Any]] = []

    gps_sources = wanted_sources - {SOURCE_MANUAL}
    if gps_sources:
        query: Dict[str, Any] = {}
        if vehicle_id:
            query["vehicle_id"] = vehicle_id
        elif vehicle_ids is not None:
            query["vehicle_id"] = {"$in": list(vehicle_ids)}
        range_filter = _range_query("start_time", start_dt, end_dt)
        if range_filter:
            query.update(range_filter)
        if not include_duplicates:
            query["duplicate_of"] = {"$in": [None, ""]}

        cursor = db.gps_trips.find(query, {"_id": 0, "route_points": 0}).sort("start_time", 1)
        for doc in await cursor.to_list(limit):
            trip = normalize_gps_trip(doc)
            if trip["source"] not in gps_sources:
                continue
            trips.append(trip)

    if include_manual and SOURCE_MANUAL in wanted_sources:
        log_query: Dict[str, Any] = {"gps_source": {"$ne": True}}
        if vehicle_id:
            log_query["vehicle_id"] = vehicle_id
        elif vehicle_ids is not None:
            log_query["vehicle_id"] = {"$in": list(vehicle_ids)}
        if date_from or date_to:
            date_filter: Dict[str, Any] = {}
            if date_from:
                date_filter["$gte"] = str(date_from)[:10]
            if date_to:
                date_filter["$lte"] = str(date_to)[:10]
            log_query["date"] = date_filter
        cursor = db.logbook.find(log_query, {"_id": 0}).sort("date", 1)
        for doc in await cursor.to_list(limit):
            trips.append(normalize_logbook_entry(doc))

    # Exact local-date filtering (the DB window is intentionally wider).
    if date_from or date_to:
        d_from = str(date_from)[:10] if date_from else None
        d_to = str(date_to)[:10] if date_to else None
        trips = [
            t
            for t in trips
            if t["date"] and (not d_from or t["date"] >= d_from) and (not d_to or t["date"] <= d_to)
        ]

    if instructor_id:
        trips = [t for t in trips if t.get("instructor_id") == instructor_id]

    trips.sort(key=lambda t: (t["start_time"] or datetime.min.replace(tzinfo=timezone.utc)))
    return trips


async def resolve_trip_instructors(db, trips: List[Dict[str, Any]]) -> None:
    """Fill in `instructor_id`/`instructor_name` and `vehicle_info` in bulk.

    GPS trips have no instructor of their own; the vehicle's assigned
    instructor is used so instructor statistics include tracker and Ruhavik
    drives, not just hand-written logbook rows. Runs two queries in total
    regardless of the number of trips (no N+1).
    """
    vehicle_ids = {t["vehicle_id"] for t in trips if t.get("vehicle_id")}
    vehicles = {}
    if vehicle_ids:
        docs = await db.vehicles.find(
            {"vehicle_id": {"$in": list(vehicle_ids)}},
            {"_id": 0, "vehicle_id": 1, "brand": 1, "model": 1, "registration_plate": 1,
             "assigned_instructor_id": 1},
        ).to_list(len(vehicle_ids) + 10)
        vehicles = {v["vehicle_id"]: v for v in docs}

    for trip in trips:
        vehicle = vehicles.get(trip.get("vehicle_id"))
        if vehicle:
            trip["vehicle_info"] = (
                f"{vehicle.get('brand', '')} {vehicle.get('model', '')} "
                f"({vehicle.get('registration_plate', '')})".strip()
            )
            if not trip.get("instructor_id"):
                trip["instructor_id"] = vehicle.get("assigned_instructor_id")
        else:
            trip.setdefault("vehicle_info", None)

    instructor_ids = {t.get("instructor_id") for t in trips if t.get("instructor_id")}
    instructors = {}
    if instructor_ids:
        docs = await db.instructors.find(
            {"instructor_id": {"$in": list(instructor_ids)}},
            {"_id": 0, "instructor_id": 1, "name": 1},
        ).to_list(len(instructor_ids) + 10)
        instructors = {i["instructor_id"]: i.get("name") for i in docs}

    for trip in trips:
        trip["instructor_name"] = instructors.get(trip.get("instructor_id"))


# ── aggregation ─────────────────────────────────────────────────

def summarize(trips: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate normalised trips into report figures.

    Every breakdown is derived from the same list, so the trip count on the
    dashboard, in the period report and in the per-vehicle report can never
    disagree.
    """
    total_km = 0.0
    by_source: Dict[str, Dict[str, Any]] = {}
    by_vehicle: Dict[str, Dict[str, Any]] = {}
    by_day: Dict[str, float] = {}
    by_instructor: Dict[str, Dict[str, Any]] = {}
    max_speed = 0

    for trip in trips:
        km = trip.get("distance_km") or 0.0
        total_km += km
        max_speed = max(max_speed, trip.get("max_speed") or 0)

        src = trip.get("source") or LEGACY_SOURCE
        bucket = by_source.setdefault(src, {"trips": 0, "distance_km": 0.0})
        bucket["trips"] += 1
        bucket["distance_km"] += km

        vid = trip.get("vehicle_id")
        if vid:
            vb = by_vehicle.setdefault(
                vid,
                {"vehicle_id": vid, "vehicle_info": trip.get("vehicle_info"), "trips": 0,
                 "distance_km": 0.0, "sources": {}},
            )
            vb["trips"] += 1
            vb["distance_km"] += km
            vb["sources"][src] = vb["sources"].get(src, 0) + 1
            if not vb.get("vehicle_info"):
                vb["vehicle_info"] = trip.get("vehicle_info")

        day = trip.get("date")
        if day:
            by_day[day] = by_day.get(day, 0.0) + km

        iid = trip.get("instructor_id")
        if iid:
            ib = by_instructor.setdefault(
                iid,
                {"instructor_id": iid, "instructor_name": trip.get("instructor_name"),
                 "trips": 0, "distance_km": 0.0},
            )
            ib["trips"] += 1
            ib["distance_km"] += km
            if not ib.get("instructor_name"):
                ib["instructor_name"] = trip.get("instructor_name")

    for bucket in by_source.values():
        bucket["distance_km"] = round(bucket["distance_km"], 1)
    for bucket in by_vehicle.values():
        bucket["distance_km"] = round(bucket["distance_km"], 1)
    for bucket in by_instructor.values():
        bucket["distance_km"] = round(bucket["distance_km"], 1)

    days = len(by_day) or 1
    return {
        "total_trips": len(trips),
        "total_distance_km": round(total_km, 1),
        "avg_distance_km": round(total_km / len(trips), 1) if trips else 0.0,
        "avg_km_per_day": round(total_km / days, 1),
        "max_speed": max_speed,
        "days_with_activity": len(by_day),
        "by_source": by_source,
        "by_vehicle": sorted(by_vehicle.values(), key=lambda v: v["distance_km"], reverse=True),
        "by_instructor": sorted(by_instructor.values(), key=lambda v: v["distance_km"], reverse=True),
        "daily": [{"date": d, "km": round(k, 1)} for d, k in sorted(by_day.items())],
    }


# ── de-duplication ──────────────────────────────────────────────

def make_external_id(source: str, vehicle_id: str, start: Any, end: Any, distance_m: Any,
                     provided_id: Optional[str] = None) -> str:
    """Stable identifier for an imported trip.

    When the export carries its own trip id that wins, which makes re-importing
    the same export a no-op. Otherwise the id is derived from the immutable
    facts of the drive, so the same file produces the same ids every time.
    """
    if provided_id:
        return f"{source}:{str(provided_id).strip()}"
    start_dt = to_utc(start)
    end_dt = to_utc(end)
    raw = "|".join([
        source,
        str(vehicle_id or ""),
        start_dt.isoformat() if start_dt else "",
        end_dt.isoformat() if end_dt else "",
        str(int(distance_m or 0)),
    ])
    return f"{source}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


def looks_like_same_drive(candidate: Dict[str, Any], existing: Dict[str, Any]) -> bool:
    """Whether two trips describe the same physical drive.

    Requires the same vehicle, both endpoints within
    :data:`DUP_TIME_TOLERANCE_MIN` minutes, and a comparable distance. Trips
    that merely happen to be similar in length, or that follow one another on
    the same day, are left alone — two real drives must never be merged.
    """
    if candidate.get("vehicle_id") != existing.get("vehicle_id"):
        return False

    c_start, c_end = to_utc(candidate.get("start_time")), to_utc(candidate.get("end_time"))
    e_start, e_end = to_utc(existing.get("start_time")), to_utc(existing.get("end_time"))
    if not (c_start and e_start):
        return False

    tolerance = timedelta(minutes=DUP_TIME_TOLERANCE_MIN)
    if abs(c_start - e_start) > tolerance:
        return False
    if c_end and e_end and abs(c_end - e_end) > tolerance:
        return False
    if bool(c_end) != bool(e_end):
        return False

    c_dist = int(candidate.get("distance") or candidate.get("distance_m") or 0)
    e_dist = int(existing.get("distance") or existing.get("distance_m") or 0)
    if c_dist or e_dist:
        allowed = max(DUP_DISTANCE_TOLERANCE_M, int(max(c_dist, e_dist) * DUP_DISTANCE_TOLERANCE_RATIO))
        if abs(c_dist - e_dist) > allowed:
            return False

    return True


async def find_duplicate_trip(db, candidate: Dict[str, Any], exclude_source: Optional[str] = None
                              ) -> Optional[Dict[str, Any]]:
    """Find an already-stored trip describing the same drive as `candidate`.

    Only trips of the same vehicle starting inside the tolerance window are
    inspected, so the check is a single indexed query per candidate.
    """
    start = to_utc(candidate.get("start_time"))
    vehicle_id = candidate.get("vehicle_id")
    if not (start and vehicle_id):
        return None

    window = timedelta(minutes=DUP_TIME_TOLERANCE_MIN)
    lo, hi = start - window, start + window
    query: Dict[str, Any] = {"vehicle_id": vehicle_id, "duplicate_of": {"$in": [None, ""]}}
    range_filter = _range_query("start_time", lo, hi)
    if range_filter:
        query.update(range_filter)
    if exclude_source:
        query["source"] = {"$ne": exclude_source}

    existing_docs = await db.gps_trips.find(query, {"_id": 0, "route_points": 0}).to_list(50)
    for existing in existing_docs:
        if existing.get("trip_id") == candidate.get("trip_id"):
            continue
        if looks_like_same_drive(candidate, existing):
            return existing
    return None
