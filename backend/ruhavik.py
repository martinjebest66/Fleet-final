"""Ruhavik export parsing and idempotent import.

Ruhavik exports come in two shapes:

  * **point exports** (GPX tracks, or a CSV of GPS fixes) — a stream of
    positions that has to be split into drives on time gaps;
  * **trip exports** (a CSV where one row already *is* one drive, with a start,
    an end and a distance).

Both end up as ordinary trips in `gps_trips` with ``source = "ruhavik"``, so
every report treats them exactly like tracker-recorded drives.

Import guarantees:
  * **idempotent** — each trip gets a stable ``external_id``; re-importing the
    same export skips what is already stored instead of duplicating it;
  * **fault tolerant** — a single unparsable row is reported and skipped, it
    never aborts the rest of the file;
  * **honest about duplicates** — a drive a tracker already recorded is stored
    with ``duplicate_of`` set so the origin is preserved while reports count
    the drive once.
"""

from __future__ import annotations

import csv as csv_module
import io
import logging
import math
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from trips import (
    SOURCE_RUHAVIK,
    find_duplicate_trip,
    make_external_id,
    to_utc,
)

logger = logging.getLogger("fleet.ruhavik")

GPX_NS = "http://www.topografix.com/GPX/1/1"

#: Default gap between two fixes that starts a new drive.
DEFAULT_TRIP_GAP_MINUTES = 15
#: Drives shorter than this are noise (a parked vehicle drifting on GPS).
MIN_TRIP_DISTANCE_M = 100

# Column aliases seen across Ruhavik CSV exports (Czech and English headings).
POINT_COLUMNS = {
    "lat": ("latitude", "lat", "šířka", "sirka", "zeměpisná šířka"),
    "lng": ("longitude", "lng", "lon", "délka", "delka", "zeměpisná délka"),
    "time": ("time", "timestamp", "datetime", "date", "čas", "cas", "datum"),
    "speed": ("speed", "velocity", "rychlost"),
}
TRIP_COLUMNS = {
    "start_time": ("start time", "start", "begin", "start_time", "začátek", "zacatek", "od"),
    "end_time": ("end time", "end", "finish", "end_time", "konec", "do"),
    "distance": ("distance", "mileage", "km", "vzdálenost", "vzdalenost", "trasa"),
    "max_speed": ("max speed", "max_speed", "maximum speed", "max. rychlost", "max rychlost"),
    "avg_speed": ("avg speed", "average speed", "avg_speed", "průměrná rychlost", "prumerna rychlost"),
    "trip_id": ("id", "trip id", "trip_id", "uid"),
    "start_lat": ("start lat", "start_lat", "start latitude"),
    "start_lng": ("start lon", "start_lng", "start_lon", "start longitude"),
    "end_lat": ("end lat", "end_lat", "end latitude"),
    "end_lng": ("end lon", "end_lng", "end_lon", "end longitude"),
    "start_address": ("start address", "start_address", "from", "odkud"),
    "end_address": ("end address", "end_address", "to", "kam"),
}


class ImportError_(Exception):
    """Raised when a whole file cannot be interpreted."""


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    radius = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _valid_fix(lat: Any, lng: Any) -> bool:
    """Reject the 0/0 'no fix' position and anything off the globe."""
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    if lat_f == 0.0 and lng_f == 0.0:
        return False
    return -90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not text or text.lower() in ("nan", "none", "null", "-", "?"):
        return None
    # Strip a trailing unit such as "12.4 km" / "80 km/h".
    cleaned = "".join(ch for ch in text if ch.isdigit() or ch in ".-+eE")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _map_columns(fieldnames: Optional[List[str]], aliases: Dict[str, Tuple[str, ...]]) -> Dict[str, str]:
    """Map logical column names to the actual headings present in the file."""
    if not fieldnames:
        return {}
    lowered = {(f or "").lower().strip(): f for f in fieldnames}
    mapping: Dict[str, str] = {}
    for logical, candidates in aliases.items():
        for candidate in candidates:
            if candidate in lowered:
                mapping[logical] = lowered[candidate]
                break
        if logical not in mapping:
            # Fall back to a prefix match ("distance (km)", "start time utc", …)
            for key, original in lowered.items():
                if any(key.startswith(candidate) for candidate in candidates):
                    mapping[logical] = original
                    break
    return mapping


# ── point-level parsing ─────────────────────────────────────────

def parse_gpx(content: str) -> List[Dict[str, Any]]:
    """Extract track points from a GPX document."""
    points: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ImportError_(f"Neplatný GPX soubor: {exc}") from exc

    trkpts = root.findall(f".//{{{GPX_NS}}}trkpt") or root.findall(".//trkpt")
    for pt in trkpts:
        lat, lng = pt.get("lat"), pt.get("lon")
        if not _valid_fix(lat, lng):
            continue
        time_el = pt.find(f"{{{GPX_NS}}}time")
        if time_el is None:
            time_el = pt.find("time")
        speed_el = pt.find(f"{{{GPX_NS}}}speed")
        if speed_el is None:
            speed_el = pt.find("speed")
        speed_kmh = 0.0
        if speed_el is not None and speed_el.text:
            raw_speed = _to_float(speed_el.text)
            if raw_speed is not None:
                speed_kmh = raw_speed * 3.6  # GPX speed is m/s
        points.append({
            "lat": float(lat),
            "lng": float(lng),
            "timestamp": time_el.text.strip() if (time_el is not None and time_el.text) else None,
            "speed": speed_kmh,
        })
    return points


def parse_point_csv(content: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse a CSV of GPS fixes. Returns (points, per-row errors)."""
    reader = csv_module.DictReader(io.StringIO(content))
    mapping = _map_columns(reader.fieldnames, POINT_COLUMNS)
    if "lat" not in mapping or "lng" not in mapping:
        raise ImportError_(
            "CSV neobsahuje sloupce se zeměpisnou šířkou/délkou (latitude/longitude)."
        )

    points: List[Dict[str, Any]] = []
    errors: List[str] = []
    for line_no, row in enumerate(reader, start=2):
        try:
            lat = _to_float(row.get(mapping["lat"]))
            lng = _to_float(row.get(mapping["lng"]))
            if not _valid_fix(lat, lng):
                errors.append(f"řádek {line_no}: chybějící nebo neplatné GPS souřadnice")
                continue
            points.append({
                "lat": lat,
                "lng": lng,
                "timestamp": (row.get(mapping["time"]) or "").strip() if "time" in mapping else None,
                "speed": _to_float(row.get(mapping.get("speed", ""), 0)) or 0.0,
            })
        except Exception as exc:  # one broken row must not stop the import
            errors.append(f"řádek {line_no}: {exc}")
    return points, errors


def points_to_trips(points: List[Dict[str, Any]], vehicle_id: str,
                    gap_minutes: int = DEFAULT_TRIP_GAP_MINUTES) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Split a stream of fixes into drives on time gaps."""
    errors: List[str] = []
    dated: List[Tuple[datetime, Dict[str, Any]]] = []
    for point in points:
        stamp = to_utc(point.get("timestamp"))
        if stamp is None:
            errors.append("bod bez použitelného časového razítka byl přeskočen")
            continue
        dated.append((stamp, point))

    if not dated:
        return [], errors

    dated.sort(key=lambda item: item[0])

    segments: List[List[Tuple[datetime, Dict[str, Any]]]] = [[dated[0]]]
    for index in range(1, len(dated)):
        gap_min = (dated[index][0] - dated[index - 1][0]).total_seconds() / 60.0
        if gap_min > gap_minutes:
            segments.append([])
        segments[-1].append(dated[index])

    result: List[Dict[str, Any]] = []
    for segment in segments:
        if len(segment) < 2:
            continue
        distance = 0.0
        for index in range(1, len(segment)):
            distance += haversine_m(
                segment[index - 1][1]["lat"], segment[index - 1][1]["lng"],
                segment[index][1]["lat"], segment[index][1]["lng"],
            )
        if distance < MIN_TRIP_DISTANCE_M:
            continue
        start_dt, start_pt = segment[0]
        end_dt, end_pt = segment[-1]
        speeds = [p.get("speed") or 0 for _, p in segment]
        duration_h = max((end_dt - start_dt).total_seconds() / 3600.0, 1e-9)
        result.append(_trip_doc(
            vehicle_id=vehicle_id,
            start=start_dt,
            end=end_dt,
            distance_m=int(distance),
            start_point={"lat": start_pt["lat"], "lng": start_pt["lng"]},
            end_point={"lat": end_pt["lat"], "lng": end_pt["lng"]},
            route_points=[
                {"lat": p["lat"], "lng": p["lng"], "timestamp": dt.isoformat()} for dt, p in segment
            ],
            max_speed=int(max(speeds)) if speeds else 0,
            avg_speed=int(round((distance / 1000.0) / duration_h)),
        ))
    return result, errors


# ── trip-level parsing ──────────────────────────────────────────

def parse_trip_csv(content: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse a Ruhavik CSV where each row already describes one drive."""
    reader = csv_module.DictReader(io.StringIO(content))
    mapping = _map_columns(reader.fieldnames, TRIP_COLUMNS)
    if "start_time" not in mapping:
        raise ImportError_("CSV neobsahuje sloupec s časem začátku jízdy.")

    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    for line_no, row in enumerate(reader, start=2):
        try:
            start = to_utc((row.get(mapping["start_time"]) or "").strip())
            if start is None:
                errors.append(f"řádek {line_no}: nečitelný čas začátku jízdy")
                continue
            end = to_utc((row.get(mapping.get("end_time", "")) or "").strip()) if "end_time" in mapping else None
            if end is not None and end < start:
                errors.append(f"řádek {line_no}: konec jízdy je před jejím začátkem")
                continue
            distance_km = _to_float(row.get(mapping.get("distance", ""))) if "distance" in mapping else None
            rows.append({
                "start": start,
                "end": end or start,
                "distance_m": int(round((distance_km or 0) * 1000)),
                "max_speed": int(_to_float(row.get(mapping.get("max_speed", ""))) or 0),
                "avg_speed": int(_to_float(row.get(mapping.get("avg_speed", ""))) or 0),
                "external_id": (row.get(mapping.get("trip_id", "")) or "").strip() or None,
                "start_lat": _to_float(row.get(mapping.get("start_lat", ""))),
                "start_lng": _to_float(row.get(mapping.get("start_lng", ""))),
                "end_lat": _to_float(row.get(mapping.get("end_lat", ""))),
                "end_lng": _to_float(row.get(mapping.get("end_lng", ""))),
                "start_address": (row.get(mapping.get("start_address", "")) or "").strip() or None,
                "end_address": (row.get(mapping.get("end_address", "")) or "").strip() or None,
            })
        except Exception as exc:
            errors.append(f"řádek {line_no}: {exc}")
    return rows, errors


def trip_rows_to_trips(rows: List[Dict[str, Any]], vehicle_id: str) -> List[Dict[str, Any]]:
    trips = []
    for row in rows:
        start_point = (
            {"lat": row["start_lat"], "lng": row["start_lng"]}
            if _valid_fix(row.get("start_lat"), row.get("start_lng")) else None
        )
        end_point = (
            {"lat": row["end_lat"], "lng": row["end_lng"]}
            if _valid_fix(row.get("end_lat"), row.get("end_lng")) else None
        )
        trips.append(_trip_doc(
            vehicle_id=vehicle_id,
            start=row["start"],
            end=row["end"],
            distance_m=row["distance_m"],
            start_point=start_point,
            end_point=end_point,
            route_points=[],
            max_speed=row["max_speed"],
            avg_speed=row["avg_speed"],
            provided_external_id=row.get("external_id"),
            start_address=row.get("start_address"),
            end_address=row.get("end_address"),
        ))
    return trips


def _trip_doc(vehicle_id: str, start: datetime, end: datetime, distance_m: int,
              start_point: Optional[dict], end_point: Optional[dict], route_points: List[dict],
              max_speed: int, avg_speed: int, provided_external_id: Optional[str] = None,
              start_address: Optional[str] = None, end_address: Optional[str] = None) -> Dict[str, Any]:
    """Build a `gps_trips` document for an imported Ruhavik drive."""
    def location(point: Optional[dict], address: Optional[str]) -> dict:
        if point:
            return {
                "lat": point["lat"],
                "lng": point["lng"],
                "address": address or f"{point['lat']:.4f}, {point['lng']:.4f}",
            }
        return {"lat": None, "lng": None, "address": address or "Ruhavik"}

    return {
        "trip_id": f"gps_{uuid.uuid4().hex[:12]}",
        "vehicle_id": vehicle_id,
        "source": SOURCE_RUHAVIK,
        "external_id": make_external_id(
            SOURCE_RUHAVIK, vehicle_id, start, end, distance_m, provided_external_id
        ),
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "start_location": location(start_point, start_address),
        "end_location": location(end_point, end_address),
        "route_points": route_points,
        "distance": int(distance_m),
        "max_speed": int(max_speed),
        "avg_speed": int(avg_speed),
        "synced_to_logbook": False,
        "duplicate_of": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ── parse entry point ───────────────────────────────────────────

def parse_ruhavik_file(filename: str, content: str, vehicle_id: str
                       ) -> Tuple[List[Dict[str, Any]], List[str], str]:
    """Parse a Ruhavik export into trip documents.

    Returns ``(trips, per-record errors, detected format)``. Raises
    :class:`ImportError_` only when the file as a whole is unusable.
    """
    name = (filename or "").lower()

    if name.endswith(".gpx") or content.lstrip().startswith("<?xml") or "<gpx" in content[:2000].lower():
        points = parse_gpx(content)
        if not points:
            raise ImportError_("GPX soubor neobsahuje žádné platné trackpointy.")
        built, errors = points_to_trips(points, vehicle_id)
        return built, errors, "gpx"

    if not name.endswith(".csv") and "," not in content[:2000] and ";" not in content[:2000]:
        raise ImportError_("Nepodporovaný formát. Nahrajte .csv nebo .gpx soubor.")

    # Trip-level exports have a start *and* an end column; anything else is a
    # stream of positions.
    header = content.splitlines()[0].lower() if content.strip() else ""
    mapping = _map_columns(header.split(","), TRIP_COLUMNS)
    is_trip_export = "start_time" in mapping and "end_time" in mapping and "distance" in mapping

    if is_trip_export:
        rows, errors = parse_trip_csv(content)
        if not rows and errors:
            raise ImportError_("Žádný řádek souboru neobsahoval platnou jízdu.")
        return trip_rows_to_trips(rows, vehicle_id), errors, "csv-trips"

    points, errors = parse_point_csv(content)
    if not points:
        raise ImportError_("Soubor neobsahuje žádné platné GPS body.")
    built, point_errors = points_to_trips(points, vehicle_id)
    return built, errors + point_errors, "csv-points"


# ── idempotent persistence ──────────────────────────────────────

async def store_trips(db, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Persist parsed trips, skipping what is already known.

    Returns a per-file report: how many drives were newly imported, how many
    were skipped as an already-imported record, how many were stored but
    flagged as a duplicate of a tracker-recorded drive, and which records were
    rejected.
    """
    imported: List[str] = []
    skipped_existing = 0
    marked_duplicate = 0
    rejected: List[str] = []

    external_ids = [t["external_id"] for t in candidates if t.get("external_id")]
    known: set = set()
    if external_ids:
        existing = await db.gps_trips.find(
            {"source": SOURCE_RUHAVIK, "external_id": {"$in": external_ids}},
            {"_id": 0, "external_id": 1},
        ).to_list(len(external_ids) + 10)
        known = {doc["external_id"] for doc in existing if doc.get("external_id")}

    seen_in_file: set = set()

    for trip in candidates:
        external_id = trip.get("external_id")
        if external_id and (external_id in known or external_id in seen_in_file):
            skipped_existing += 1
            continue
        try:
            duplicate = await find_duplicate_trip(db, trip, exclude_source=SOURCE_RUHAVIK)
            if duplicate:
                # Keep the record (the origin information stays) but mark it so
                # the reporting layer counts the drive exactly once.
                trip["duplicate_of"] = duplicate["trip_id"]
                trip["duplicate_reason"] = "shodná jízda již zaznamenána trackerem"
                marked_duplicate += 1
            await db.gps_trips.insert_one(dict(trip))
            imported.append(trip["trip_id"])
            if external_id:
                seen_in_file.add(external_id)
        except Exception as exc:
            logger.warning("Ruhavik: záznam nebyl uložen (%s): %s", trip.get("external_id"), exc)
            rejected.append(f"{trip.get('start_time')}: {exc}")

    return {
        "imported": len(imported) - marked_duplicate,
        "imported_total": len(imported),
        "duplicates_of_tracker": marked_duplicate,
        "skipped_already_imported": skipped_existing,
        "rejected": len(rejected),
        "rejected_details": rejected[:20],
        "trip_ids": imported,
    }
