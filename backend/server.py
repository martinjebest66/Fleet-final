from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import io
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, field_validator
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import httpx
import base64
import secrets
import struct
import bcrypt
import jwt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from teltonika import (
    OBD_IO_MAP,
    PARAM_FUEL_LEVEL_LITERS,
    PARAM_FUEL_LEVEL_PERCENT,
    PARAM_TRACKER_MILEAGE,
    PARAM_VEHICLE_MILEAGE,
    TeltonikaTCPServer,
    build_avl_packet,
    build_imei_packet,
    build_param_io_map,
    extract_vehicle_parameters,
)
import resend
import asyncio
import csv as csv_module

from pymongo.errors import BulkWriteError, PyMongoError

import database
import ruhavik as ruhavik_import
import trips as trips_service
import vehicle_state
from config import ConfigError, settings

ROOT_DIR = Path(__file__).parent

# Configure logging before anything else so startup problems are visible in
# `docker compose logs`.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("fleet.api")

# MongoDB handle. The connection itself is established lazily and verified
# during startup (see `startup_tasks`), so an unavailable database delays
# readiness instead of crashing the import.
db = database.get_db()

app = FastAPI(
    title="Fleet Manager API",
    description="Správa vozového parku autoškoly",
    version="1.1.0",
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# ======================== MODELS ========================

# User models
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: str = "admin"  # admin, instructor
    created_at: datetime

class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: str

# Vehicle models
class VehicleCreate(BaseModel):
    registration_plate: str
    brand: str
    model: str
    year: int
    vin: Optional[str] = None
    odometer: int = 0
    fuel_type: str = "benzín"  # benzín, nafta, LPG, elektro
    assigned_instructor_id: Optional[str] = None
    reservation_alias: Optional[str] = None  # název vozidla v rezervačním systému

class Vehicle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    vehicle_id: str
    registration_plate: str
    brand: str
    model: str
    year: int
    vin: Optional[str] = None
    odometer: int = 0
    fuel_type: str
    assigned_instructor_id: Optional[str] = None
    reservation_alias: Optional[str] = None
    qr_code_fuel: str
    qr_code_damage: str
    qr_code_handover: Optional[str] = None
    created_at: datetime
    updated_at: datetime

# Instructor models
class InstructorCreate(BaseModel):
    name: str
    email: str
    phone: str
    license_number: str
    assigned_vehicle_ids: List[str] = Field(default_factory=list)
    pin: Optional[str] = None  # 4-6 digit PIN for instructor login; blank keeps the current one
    ics_url: Optional[str] = None  # statický odkaz na ICS kalendář učitele

    @field_validator("pin")
    @classmethod
    def _validate_pin(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        value = value.strip()
        if not value.isdigit() or not (4 <= len(value) <= 6):
            raise ValueError("PIN musí být 4 až 6 číslic")
        return value

    @field_validator("ics_url")
    @classmethod
    def _validate_ics_url(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        value = value.strip()
        if not value:
            return None
        if not value.lower().startswith(("http://", "https://", "webcal://")):
            raise ValueError("ICS odkaz musí začínat http://, https:// nebo webcal://")
        return value

class Instructor(BaseModel):
    """Instructor as returned by the API.

    The PIN is intentionally absent: it is a login credential and is stored
    hashed. Clients only need to know whether one is set.
    """
    model_config = ConfigDict(extra="ignore")
    instructor_id: str
    name: str
    email: str
    phone: str
    license_number: str
    assigned_vehicle_ids: List[str] = []
    has_pin: bool = False
    ics_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

# Logbook (Kniha jízd) models
class LogbookEntryCreate(BaseModel):
    vehicle_id: str
    instructor_id: Optional[str] = None
    date: str  # ISO date string
    start_time: str
    end_time: str
    start_location: str
    end_location: str
    route_description: str
    start_odometer: int
    end_odometer: int
    purpose: str  # výcvik, služební, soukromá
    notes: Optional[str] = None

class LogbookEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entry_id: str
    vehicle_id: str
    instructor_id: Optional[str] = None
    instructor_name: Optional[str] = None
    vehicle_info: Optional[str] = None
    date: str
    start_time: str
    end_time: str
    start_location: str
    end_location: str
    route_description: str
    start_odometer: int
    end_odometer: int
    distance: int
    purpose: str
    notes: Optional[str] = None
    gps_source: bool = False
    created_at: datetime

# Fuel entry models
class FuelEntryCreate(BaseModel):
    vehicle_id: str
    date: str
    odometer: int
    liters: float
    price_per_liter: float
    total_price: float
    fuel_station: Optional[str] = None
    notes: Optional[str] = None

class FuelEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    fuel_id: str
    vehicle_id: str
    vehicle_info: Optional[str] = None
    date: str
    odometer: int
    liters: float
    price_per_liter: float
    total_price: float
    fuel_station: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

# Damage report models
class DamageReportCreate(BaseModel):
    vehicle_id: str
    description: str
    severity: str  # nízká, střední, vysoká
    location_on_vehicle: str
    photos: List[str] = []
    reported_by: Optional[str] = None
    notes: Optional[str] = None

class DamageReport(BaseModel):
    model_config = ConfigDict(extra="ignore")
    damage_id: str
    vehicle_id: str
    vehicle_info: Optional[str] = None
    description: str
    severity: str
    location_on_vehicle: str
    photos: List[str] = []
    reported_by: Optional[str] = None
    notes: Optional[str] = None
    status: str = "otevřeno"  # otevřeno, v řešení, vyřešeno
    created_at: datetime
    resolved_at: Optional[datetime] = None

# Handover protocol models
class HandoverProtocolCreate(BaseModel):
    vehicle_id: str
    instructor_id: str
    type: str  # převzetí, předání
    odometer: int
    fuel_level: int  # percentage
    exterior_condition: str
    interior_condition: str
    damages_noted: List[str] = []
    photos: List[str] = []
    notes: Optional[str] = None

class HandoverProtocol(BaseModel):
    model_config = ConfigDict(extra="ignore")
    handover_id: str
    vehicle_id: str
    vehicle_info: Optional[str] = None
    instructor_id: str
    instructor_name: Optional[str] = None
    type: str
    odometer: int
    fuel_level: int
    exterior_condition: str
    interior_condition: str
    damages_noted: List[str] = []
    photos: List[str] = []
    notes: Optional[str] = None
    created_at: datetime

# GPS Trip models
class GPSTrip(BaseModel):
    model_config = ConfigDict(extra="ignore")
    trip_id: str
    vehicle_id: str
    vehicle_info: Optional[str] = None
    # Origin of the drive: teltonika | ruhavik | manual | mock. Always present
    # so a report can tell where a trip came from without guessing.
    source: str = trips_service.SOURCE_TELTONIKA
    duplicate_of: Optional[str] = None
    start_time: datetime
    end_time: datetime
    start_location: dict  # {lat, lng, address}
    end_location: dict
    route_points: List[dict] = []  # [{lat, lng, timestamp}]
    distance: int  # meters
    max_speed: int  # km/h
    avg_speed: int
    synced_to_logbook: bool = False
    created_at: datetime

# QR Handover Protocol models (mobile form submission)
class FluidChecks(BaseModel):
    engine_oil: bool = False
    coolant: bool = False
    brake_fluid: bool = False
    windshield_washer: bool = False
    other_fluids: bool = False
    other_fluids_note: Optional[str] = None

class HandoverPhoto(BaseModel):
    photo_type: str  # front, rear, left, right, interior, dashboard
    photo_url: str
    timestamp: str

class QRHandoverCreate(BaseModel):
    vehicle_id: str
    handler_name: str
    handler_type: str  # převzetí (takeover), předání (handover)
    odometer: int
    fuel_level: int  # percentage from dashboard photo
    fluid_checks: FluidChecks
    photos: List[HandoverPhoto]
    notes: Optional[str] = None

class QRHandover(BaseModel):
    model_config = ConfigDict(extra="ignore")
    qr_handover_id: str
    vehicle_id: str
    vehicle_info: Optional[str] = None
    handler_name: str
    handler_type: str
    odometer: int
    fuel_level: int
    fluid_checks: dict
    photos: List[dict]
    notes: Optional[str] = None
    created_at: datetime


class GPSDeviceCreate(BaseModel):
    imei: str
    vehicle_id: str
    name: Optional[str] = None


class GPSDevice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    device_id: str
    imei: str
    vehicle_id: str
    vehicle_info: Optional[str] = None
    name: Optional[str] = None
    last_seen: Optional[datetime] = None
    status: str = "offline"
    created_at: datetime


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class InstructorLoginRequest(BaseModel):
    instructor_id: str
    pin: str


# Maintenance models
class MaintenanceItemCreate(BaseModel):
    vehicle_id: str
    type: str  # STK, olej, pneumatiky, brzdy, rozvodový řemen, vlastní
    custom_label: Optional[str] = None
    last_done_date: Optional[str] = None
    last_done_odometer: Optional[int] = None
    interval_months: Optional[int] = None
    interval_km: Optional[int] = None
    next_due_date: Optional[str] = None
    next_due_odometer: Optional[int] = None
    notes: Optional[str] = None


MAINTENANCE_DOC_TYPES = ("faktura", "STK protokol", "servisní kniha", "účtenka", "foto", "jiné")


class MaintenanceDocument(BaseModel):
    """Metadata of a photographed service/maintenance document.

    The image itself lives in its own collection and is fetched through
    `/maintenance/documents/{id}/file`; keeping it out of the maintenance
    record stops a handful of phone photos from bloating every list response
    (and from running into the 16 MB BSON document limit).
    """
    model_config = ConfigDict(extra="ignore")
    document_id: str
    doc_type: str = "foto"
    label: Optional[str] = None
    filename: Optional[str] = None
    content_type: str = "image/jpeg"
    size_bytes: int = 0
    url: str
    uploaded_at: datetime
    uploaded_by: Optional[str] = None


class MaintenanceItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    maintenance_id: str
    vehicle_id: str
    vehicle_info: Optional[str] = None
    type: str
    custom_label: Optional[str] = None
    last_done_date: Optional[str] = None
    last_done_odometer: Optional[int] = None
    interval_months: Optional[int] = None
    interval_km: Optional[int] = None
    next_due_date: Optional[str] = None
    next_due_odometer: Optional[int] = None
    status: str = "ok"  # ok, blíží se, po termínu
    notes: Optional[str] = None
    documents: List[MaintenanceDocument] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ======================== PASSWORD & JWT HELPERS ========================

JWT_ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_MAX_AGE = settings.access_token_hours * 3600
REFRESH_TOKEN_MAX_AGE = settings.refresh_token_days * 86400
SESSION_MAX_AGE = settings.session_days * 86400


def get_jwt_secret() -> str:
    """Return the configured JWT secret.

    There is deliberately no fallback value: a build-in default secret would
    let anyone who has read this repository mint valid tokens. Startup refuses
    to run without one, so reaching this error means the process was started
    outside the normal path.
    """
    if not settings.jwt_secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET není nakonfigurován")
    return settings.jwt_secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Stored value is not a bcrypt hash (legacy/corrupt record).
        return False


def _is_bcrypt_hash(value: Optional[str]) -> bool:
    return bool(value) and value.startswith(("$2a$", "$2b$", "$2y$"))


def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.access_token_hours),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def _cookie_kwargs(max_age: int) -> dict:
    """Cookie attributes derived from configuration.

    The previous hard-coded ``Secure`` + ``SameSite=None`` combination is
    rejected by browsers over plain HTTP, which is the default for a Docker
    deployment behind Nginx: the login request succeeded but the cookie was
    never stored, so every following request came back 401 and the UI looked
    like "the data does not load". The attributes now follow the deployment:
    same-origin over HTTP by default, ``Secure`` once TLS is configured.
    """
    kwargs = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "max_age": max_age,
        "path": "/",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie(key="access_token", value=access_token, **_cookie_kwargs(ACCESS_TOKEN_MAX_AGE))
    response.set_cookie(key="refresh_token", value=refresh_token, **_cookie_kwargs(REFRESH_TOKEN_MAX_AGE))


def _clear_auth_cookies(response: Response):
    for name in ("session_token", "access_token", "refresh_token"):
        response.delete_cookie(
            key=name,
            path="/",
            domain=settings.cookie_domain or None,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
        )


# ── Brute-force protection ──────────────────────────────────────
# Small in-process sliding window. The deployment runs a single Uvicorn worker
# per container, which is what this protects; a multi-node setup should put a
# rate limit in front of the app as well.
_login_attempts: dict = {}


def _rate_limit_key(request: Request, identifier: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_host = forwarded.split(",")[0].strip()
    return f"{client_host}|{identifier}"


def check_login_rate_limit(request: Request, identifier: str) -> None:
    """Raise 429 when an identifier/IP pair exceeds the configured attempts."""
    now = datetime.now(timezone.utc).timestamp()
    window = settings.login_rate_limit_window_sec
    key = _rate_limit_key(request, identifier)

    attempts = [ts for ts in _login_attempts.get(key, []) if now - ts < window]
    if len(attempts) >= settings.login_rate_limit_attempts:
        retry_after = int(window - (now - attempts[0])) + 1
        logger.warning("Rate limit hit for login attempt (key hash %s)", hash(key) & 0xFFFF)
        raise HTTPException(
            status_code=429,
            detail="Příliš mnoho pokusů o přihlášení. Zkuste to prosím později.",
            headers={"Retry-After": str(max(1, retry_after))},
        )
    _login_attempts[key] = attempts


def record_failed_login(request: Request, identifier: str) -> None:
    key = _rate_limit_key(request, identifier)
    now = datetime.now(timezone.utc).timestamp()
    window = settings.login_rate_limit_window_sec
    attempts = [ts for ts in _login_attempts.get(key, []) if now - ts < window]
    attempts.append(now)
    _login_attempts[key] = attempts
    if len(_login_attempts) > 10000:  # bound memory on a hostile client
        cutoff = now - window
        for stale_key in [k for k, v in _login_attempts.items() if not v or v[-1] < cutoff]:
            _login_attempts.pop(stale_key, None)


def clear_login_attempts(request: Request, identifier: str) -> None:
    _login_attempts.pop(_rate_limit_key(request, identifier), None)


# ======================== HELPERS ========================

# Image formats accepted from a phone camera. HEIC/HEIF are what an iPhone
# produces by default.
ALLOWED_UPLOAD_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}



def parse_datetime_field(doc: dict, field: str):
    """Convert an ISO string field to datetime in-place if needed."""
    val = doc.get(field)
    if isinstance(val, str):
        doc[field] = datetime.fromisoformat(val)


def parse_expires_at(value) -> datetime:
    """Parse expiry value into a timezone-aware datetime."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _vehicle_label(vehicle: dict) -> str:
    return f"{vehicle.get('brand', '')} {vehicle.get('model', '')} ({vehicle.get('registration_plate', '')})".strip()


async def enrich_vehicle_info(doc: dict):
    """Add vehicle_info string to a document that has vehicle_id."""
    vehicle = await db.vehicles.find_one({"vehicle_id": doc.get("vehicle_id")}, {"_id": 0})
    if vehicle:
        doc["vehicle_info"] = _vehicle_label(vehicle)


async def enrich_instructor_name(doc: dict):
    """Add instructor_name to a document that has instructor_id."""
    if doc.get("instructor_id"):
        instructor = await db.instructors.find_one({"instructor_id": doc["instructor_id"]}, {"_id": 0})
        if instructor:
            doc["instructor_name"] = instructor["name"]


async def enrich_many(docs: List[dict], with_instructor: bool = False) -> List[dict]:
    """Attach vehicle (and optionally instructor) labels to a list of documents.

    Two queries in total, regardless of list length. The per-document helpers
    above issued one query per row, which meant a thousand round trips for a
    single logbook page.
    """
    if not docs:
        return docs

    vehicle_ids = {d.get("vehicle_id") for d in docs if d.get("vehicle_id")}
    if vehicle_ids:
        vehicles = await db.vehicles.find(
            {"vehicle_id": {"$in": list(vehicle_ids)}},
            {"_id": 0, "vehicle_id": 1, "brand": 1, "model": 1, "registration_plate": 1},
        ).to_list(len(vehicle_ids) + 10)
        labels = {v["vehicle_id"]: _vehicle_label(v) for v in vehicles}
        for doc in docs:
            label = labels.get(doc.get("vehicle_id"))
            if label:
                doc["vehicle_info"] = label

    if with_instructor:
        instructor_ids = {d.get("instructor_id") for d in docs if d.get("instructor_id")}
        if instructor_ids:
            instructors = await db.instructors.find(
                {"instructor_id": {"$in": list(instructor_ids)}},
                {"_id": 0, "instructor_id": 1, "name": 1},
            ).to_list(len(instructor_ids) + 10)
            names = {i["instructor_id"]: i.get("name") for i in instructors}
            for doc in docs:
                name = names.get(doc.get("instructor_id"))
                if name:
                    doc["instructor_name"] = name
    return docs


# ======================== EMAIL NOTIFICATION HELPER ========================

resend_api_key = os.environ.get("RESEND_API_KEY")
if resend_api_key:
    resend.api_key = resend_api_key

sender_email = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")


async def send_damage_notification(damage_report: dict, vehicle_info: str):
    """Send email notification to admin when a damage report is created."""
    if not resend_api_key:
        logger.info("RESEND_API_KEY not set, skipping email notification")
        return
    admin_email = os.environ.get("ADMIN_EMAIL")
    if not admin_email:
        return
    severity_colors = {"nízká": "#16A34A", "střední": "#FFC000", "vysoká": "#FF2400"}
    color = severity_colors.get(damage_report.get("severity", ""), "#52525B")
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;border:1px solid #E4E4E7;border-radius:8px;overflow:hidden;">
      <div style="background:#002FA7;color:white;padding:20px;">
        <h2 style="margin:0;">Nové hlášení poškození</h2>
      </div>
      <div style="padding:20px;">
        <p><strong>Vozidlo:</strong> {vehicle_info}</p>
        <p><strong>Závažnost:</strong> <span style="color:{color};font-weight:bold;">{damage_report.get('severity','')}</span></p>
        <p><strong>Popis:</strong> {damage_report.get('description','')}</p>
        <p><strong>Umístění:</strong> {damage_report.get('location_on_vehicle','')}</p>
        <p><strong>Nahlásil:</strong> {damage_report.get('reported_by','Neznámý')}</p>
        <p style="color:#52525B;font-size:12px;">Datum: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')}</p>
      </div>
    </div>
    """
    try:
        params = {
            "from": sender_email,
            "to": [admin_email],
            "subject": f"[Fleet Manager] Poškození: {vehicle_info} ({damage_report.get('severity','')})",
            "html": html
        }
        await asyncio.to_thread(resend.Emails.send, params)
        logger.info("Notifikace o poškození odeslána na %s", admin_email)
    except Exception:
        # A failing notification must never block the damage report itself, but
        # the cause has to be visible in the log.
        logger.exception("Odeslání e-mailu o poškození selhalo")


def compute_maintenance_status(item: dict) -> str:
    """Compute status for a maintenance item: ok, blíží se, po termínu."""
    today = datetime.now(timezone.utc).date()
    next_date = item.get("next_due_date")
    if next_date:
        try:
            due = datetime.fromisoformat(next_date).date() if isinstance(next_date, str) else next_date
            diff = (due - today).days
            if diff < 0:
                return "po termínu"
            if diff <= 30:
                return "blíží se"
        except (ValueError, TypeError):
            pass
    return "ok"


def extract_session_token(request: Request) -> str:
    """Extract session token from cookie or Authorization header."""
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    return token


async def validate_session(session_token: str) -> dict:
    """Validate session token and return session doc. Raises HTTPException on failure."""
    session_doc = await db.user_sessions.find_one(
        {"session_token": session_token}, {"_id": 0}
    )
    if not session_doc:
        raise HTTPException(status_code=401, detail="Neplatná relace")

    expires_at = parse_expires_at(session_doc["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Relace vypršela")

    return session_doc


# ======================== AUTH HELPERS ========================

async def _try_jwt_auth(request: Request) -> Optional[User]:
    """Try JWT-based auth. Returns User or None."""
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        user_id = payload["sub"]
        role = payload.get("role", "admin")

        if role == "instructor":
            instr = await db.instructors.find_one({"instructor_id": user_id}, {"_id": 0})
            if not instr:
                return None
            parse_datetime_field(instr, "created_at")
            return User(
                user_id=instr["instructor_id"],
                email=instr.get("email", ""),
                name=instr["name"],
                role="instructor",
                created_at=instr["created_at"],
            )
        else:
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                return None
            parse_datetime_field(user_doc, "created_at")
            return User(**user_doc)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
    except (KeyError, ValueError, TypeError):
        # Malformed token payload — treat as "not authenticated by JWT" and let
        # session auth have a go, but record it: a burst of these is a bug.
        logger.warning("Nečitelný obsah JWT tokenu", exc_info=True)
        return None


async def _try_session_auth(request: Request) -> Optional[User]:
    """Try session-token-based auth (Emergent Google OAuth). Returns User or None."""
    session_token = extract_session_token(request)
    if not session_token:
        return None
    try:
        session_doc = await validate_session(session_token)
        user_doc = await db.users.find_one({"user_id": session_doc["user_id"]}, {"_id": 0})
        if not user_doc:
            return None
        parse_datetime_field(user_doc, "created_at")
        return User(**user_doc)
    except HTTPException:
        return None


async def get_current_user(request: Request) -> User:
    """Get current user from JWT or session token."""
    user = await _try_jwt_auth(request)
    if user:
        return user
    user = await _try_session_auth(request)
    if user:
        return user
    raise HTTPException(status_code=401, detail="Nepřihlášen")


async def get_admin_user(request: Request) -> User:
    """Get current user and ensure admin role."""
    user = await get_current_user(request)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Přístup odmítnut - pouze admin")
    return user

# ======================== AUTH ROUTES ========================

async def _fetch_emergent_session(session_id: str) -> dict:
    """Call Emergent Auth to validate session_id and return session data."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as http_client:
            auth_response = await http_client.get(
                settings.emergent_auth_url,
                headers={"X-Session-ID": session_id},
            )
    except httpx.HTTPError as exc:
        logger.error("Ověření OAuth session selhalo: %s", exc)
        raise HTTPException(status_code=502, detail="Ověřovací službu se nepodařilo kontaktovat") from exc

    if auth_response.status_code != 200:
        logger.info("OAuth session odmítnuta poskytovatelem (HTTP %s)", auth_response.status_code)
        raise HTTPException(status_code=401, detail="Neplatný session_id")
    try:
        data = auth_response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Neplatná odpověď ověřovací služby") from exc
    if not data.get("email") or not data.get("session_token"):
        raise HTTPException(status_code=502, detail="Neúplná odpověď ověřovací služby")
    return data


async def _upsert_user(session_data: dict) -> str:
    """Find or create user from Emergent session data. Returns user_id."""
    email = session_data["email"]
    existing_user = await db.users.find_one({"email": email}, {"_id": 0})

    if existing_user:
        user_id = existing_user["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": session_data["name"], "picture": session_data.get("picture")}}
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": session_data["name"],
            "picture": session_data.get("picture"),
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    return user_id


async def _create_user_session(user_id: str, session_token: str) -> datetime:
    """Replace existing sessions and create a new one. Returns expiry datetime."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return expires_at


@api_router.post("/auth/session")
async def process_session(request: Request, response: Response):
    """Process session_id from Emergent Auth and establish session"""
    data = await request.json()
    session_id = data.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Chybí session_id")

    session_data = await _fetch_emergent_session(session_id)
    user_id = await _upsert_user(session_data)
    await _create_user_session(user_id, session_data["session_token"])

    response.set_cookie(
        key="session_token",
        value=session_data["session_token"],
        **_cookie_kwargs(SESSION_MAX_AGE),
    )

    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return UserResponse(**user_doc)


@api_router.post("/auth/login")
async def admin_login(data: AdminLoginRequest, request: Request, response: Response):
    """Admin login with email/password."""
    email = data.email.lower().strip()
    check_login_rate_limit(request, email)

    user_doc = await db.users.find_one({"email": email}, {"_id": 0})
    if not user_doc or not verify_password(data.password, user_doc.get("password_hash") or ""):
        record_failed_login(request, email)
        # Deliberately identical message for "unknown user" and "wrong
        # password" so the endpoint cannot be used to enumerate accounts.
        logger.info("Neúspěšné přihlášení pro %s", email)
        raise HTTPException(status_code=401, detail="Neplatné přihlašovací údaje")

    clear_login_attempts(request, email)
    access = create_access_token(user_doc["user_id"], user_doc.get("role", "admin"))
    refresh = create_refresh_token(user_doc["user_id"])
    _set_auth_cookies(response, access, refresh)
    logger.info("Přihlášen uživatel %s (role %s)", email, user_doc.get("role", "admin"))

    return {
        "user_id": user_doc["user_id"],
        "email": user_doc["email"],
        "name": user_doc["name"],
        "role": user_doc.get("role", "admin"),
    }


async def verify_instructor_pin(instructor: dict, pin: str) -> bool:
    """Check an instructor PIN, upgrading legacy plaintext PINs on success.

    PINs used to be stored in clear text. They are hashed from now on; an
    existing plaintext PIN still authenticates once and is immediately
    replaced by its hash, so no instructor is locked out by the change.
    """
    stored = instructor.get("pin")
    if not stored:
        return False
    if _is_bcrypt_hash(stored):
        return verify_password(pin, stored)
    if secrets.compare_digest(str(stored), str(pin)):
        await db.instructors.update_one(
            {"instructor_id": instructor["instructor_id"]},
            {"$set": {"pin": hash_password(pin)}},
        )
        logger.info("PIN instruktora %s byl převeden na hash", instructor["instructor_id"])
        return True
    return False


@api_router.post("/auth/instructor-login")
async def instructor_login(data: InstructorLoginRequest, request: Request, response: Response):
    """Instructor login with ID + PIN."""
    check_login_rate_limit(request, f"instr:{data.instructor_id}")

    instructor = await db.instructors.find_one(
        {"instructor_id": data.instructor_id}, {"_id": 0}
    )
    if not instructor or not await verify_instructor_pin(instructor, data.pin):
        record_failed_login(request, f"instr:{data.instructor_id}")
        logger.info("Neúspěšné přihlášení instruktora %s", data.instructor_id)
        raise HTTPException(status_code=401, detail="Neplatné přihlašovací údaje")

    clear_login_attempts(request, f"instr:{data.instructor_id}")
    access = create_access_token(instructor["instructor_id"], "instructor")
    refresh = create_refresh_token(instructor["instructor_id"])
    _set_auth_cookies(response, access, refresh)
    logger.info("Přihlášen instruktor %s", instructor["instructor_id"])

    return {
        "user_id": instructor["instructor_id"],
        "email": instructor.get("email", ""),
        "name": instructor["name"],
        "role": "instructor",
    }


@api_router.get("/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    """Get current authenticated user"""
    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "role": user.role,
    }

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout user and clear session"""
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_many({"session_token": session_token})

    _clear_auth_cookies(response)
    return {"message": "Odhlášeno"}


@api_router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    """Refresh access token using refresh token"""
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Chybí refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Neplatný token")
        user_id = payload["sub"]

        # Determine role
        user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if user_doc:
            role = user_doc.get("role", "admin")
        else:
            instr = await db.instructors.find_one({"instructor_id": user_id}, {"_id": 0})
            role = "instructor" if instr else "admin"

        access = create_access_token(user_id, role)
        response.set_cookie(key="access_token", value=access, **_cookie_kwargs(ACCESS_TOKEN_MAX_AGE))
        return {"message": "Token obnoven"}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token vypršel")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Neplatný refresh token")


@api_router.get("/auth/instructors-list")
async def get_instructors_for_login():
    """Public endpoint - list instructors for PIN login (only id + name, no sensitive data)."""
    instructors = await db.instructors.find(
        {"pin": {"$exists": True, "$ne": None}},
        {"_id": 0, "instructor_id": 1, "name": 1}
    ).to_list(100)
    return instructors

# ======================== VEHICLE ROUTES ========================

@api_router.get("/vehicles", response_model=List[Vehicle])
async def get_vehicles(user: User = Depends(get_current_user)):
    """Get all vehicles"""
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(1000)
    for v in vehicles:
        parse_datetime_field(v, "created_at")
        parse_datetime_field(v, "updated_at")
        if not v.get('qr_code_handover'):
            v['qr_code_handover'] = f"handover_{v['vehicle_id']}"
    return vehicles

@api_router.get("/vehicles/{vehicle_id}", response_model=Vehicle)
async def get_vehicle(vehicle_id: str, user: User = Depends(get_current_user)):
    """Get a single vehicle"""
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    parse_datetime_field(vehicle, "created_at")
    parse_datetime_field(vehicle, "updated_at")
    if not vehicle.get('qr_code_handover'):
        vehicle['qr_code_handover'] = f"handover_{vehicle['vehicle_id']}"
    return Vehicle(**vehicle)

@api_router.post("/vehicles", response_model=Vehicle)
async def create_vehicle(data: VehicleCreate, user: User = Depends(get_admin_user)):
    """Create a new vehicle"""
    vehicle_id = f"veh_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    
    vehicle = {
        "vehicle_id": vehicle_id,
        **data.model_dump(),
        "qr_code_fuel": f"fuel_{vehicle_id}",
        "qr_code_damage": f"damage_{vehicle_id}",
        "qr_code_handover": f"handover_{vehicle_id}",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    }
    
    await db.vehicles.insert_one(vehicle)
    vehicle['created_at'] = now
    vehicle['updated_at'] = now
    return Vehicle(**vehicle)

@api_router.put("/vehicles/{vehicle_id}", response_model=Vehicle)
async def update_vehicle(vehicle_id: str, data: VehicleCreate, user: User = Depends(get_admin_user)):
    """Update a vehicle"""
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    now = datetime.now(timezone.utc)
    update_data = {
        **data.model_dump(),
        "updated_at": now.isoformat()
    }
    
    await db.vehicles.update_one(
        {"vehicle_id": vehicle_id},
        {"$set": update_data}
    )
    
    updated = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    parse_datetime_field(updated, "created_at")
    updated['updated_at'] = now
    return Vehicle(**updated)

@api_router.delete("/vehicles/{vehicle_id}")
async def delete_vehicle(vehicle_id: str, user: User = Depends(get_admin_user)):
    """Delete a vehicle"""
    result = await db.vehicles.delete_one({"vehicle_id": vehicle_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    return {"message": "Vozidlo smazáno"}

# ── Odometer and fuel history ──
# "What was the odometer and the fuel level of this car on that date?"
# Readings are derived from records the application already keeps (tracker
# positions, refuelling, handovers, logbook) — see backend/vehicle_state.py.

def _serialize_reading(reading: dict) -> dict:
    out = dict(reading)
    for field in ("at",):
        value = out.get(field)
        if isinstance(value, datetime):
            out[field] = value.isoformat()
    return out


@api_router.get("/vehicles/{vehicle_id}/state")
async def get_vehicle_state_at(
    vehicle_id: str,
    at: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """Odometer and fuel level of a vehicle at a moment in time.

    `at` accepts a date (`2026-08-20`) or a full timestamp; without it the
    current state is returned. The answer always says which record it came
    from, and whether the odometer is a written-down reading or an estimate
    extrapolated from tracker distance.
    """
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    if at:
        moment = trips_service.to_utc(at if "T" in at or " " in at else f"{at}T23:59:59")
        if moment is None:
            raise HTTPException(
                status_code=400,
                detail="Neplatný formát parametru 'at'. Použijte YYYY-MM-DD nebo YYYY-MM-DDTHH:MM.",
            )
    else:
        moment = datetime.now(timezone.utc)

    readings = await vehicle_state.collect_readings(
        db, vehicle_id, date_to=trips_service.local_date_of(moment)
    )
    state = vehicle_state.state_at(readings, moment)

    return {
        "vehicle_id": vehicle_id,
        "vehicle_info": _vehicle_label(vehicle),
        "registration_plate": vehicle.get("registration_plate"),
        "current_odometer": vehicle.get("odometer"),
        **{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in state.items()},
        "readings_considered": len(readings),
    }


@api_router.get("/vehicles/{vehicle_id}/state/history")
async def get_vehicle_state_history(
    vehicle_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_gps: bool = True,
    max_points: int = Query(500, ge=10, le=5000),
    user: User = Depends(get_current_user),
):
    """Odometer/fuel readings over a period, plus a per-day summary.

    The tracker stream is thinned for display only — nothing is removed from
    storage, and every hand-written reading is always kept.
    """
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    if not date_to:
        date_to = datetime.now(timezone.utc).astimezone(trips_service.REPORT_TZ).date().isoformat()
    if not date_from:
        date_from = (
            datetime.now(timezone.utc) - timedelta(days=30)
        ).astimezone(trips_service.REPORT_TZ).date().isoformat()

    readings = await vehicle_state.collect_readings(
        db, vehicle_id, date_from=date_from, date_to=date_to, include_gps=include_gps
    )
    in_window = [
        r for r in readings
        if r["date"] and date_from <= r["date"] <= date_to
    ]
    daily = vehicle_state.daily_summary(in_window)
    shown = vehicle_state.downsample(in_window, max_points)

    return {
        "vehicle_id": vehicle_id,
        "vehicle_info": _vehicle_label(vehicle),
        "date_from": date_from,
        "date_to": date_to,
        "readings": [_serialize_reading(r) for r in shown],
        "total_readings": len(in_window),
        "downsampled": len(shown) < len(in_window),
        "daily": daily,
        "sources": sorted({r["source"] for r in in_window}),
    }


# Public endpoint for QR code vehicle info
@api_router.get("/public/vehicle/{qr_code}")
async def get_vehicle_by_qr(qr_code: str):
    """Get vehicle info by QR code (public endpoint for mobile)"""
    # Check if it's a fuel, damage, or handover QR code
    qr_type = None
    if qr_code.startswith("fuel_"):
        vehicle_id = qr_code.replace("fuel_", "")
        qr_type = "fuel"
    elif qr_code.startswith("damage_"):
        vehicle_id = qr_code.replace("damage_", "")
        qr_type = "damage"
    elif qr_code.startswith("handover_"):
        vehicle_id = qr_code.replace("handover_", "")
        qr_type = "handover"
    else:
        raise HTTPException(status_code=400, detail="Neplatný QR kód")
    
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    return {
        "vehicle_id": vehicle["vehicle_id"],
        "registration_plate": vehicle["registration_plate"],
        "brand": vehicle["brand"],
        "model": vehicle["model"],
        "odometer": vehicle["odometer"],
        "fuel_type": vehicle.get("fuel_type", "benzín"),
        "qr_type": qr_type
    }

# ======================== INSTRUCTOR ROUTES ========================

def _instructor_response(doc: dict) -> dict:
    """Shape an instructor document for the API, dropping the PIN."""
    out = {k: v for k, v in doc.items() if k not in ("pin", "_id")}
    out["has_pin"] = bool(doc.get("pin"))
    parse_datetime_field(out, "created_at")
    parse_datetime_field(out, "updated_at")
    return out


@api_router.get("/instructors", response_model=List[Instructor])
async def get_instructors(user: User = Depends(get_current_user)):
    """Get all instructors"""
    instructors = await db.instructors.find({}, {"_id": 0}).to_list(1000)
    return [_instructor_response(i) for i in instructors]

@api_router.get("/instructors/{instructor_id}", response_model=Instructor)
async def get_instructor(instructor_id: str, user: User = Depends(get_current_user)):
    """Get a single instructor"""
    instructor = await db.instructors.find_one({"instructor_id": instructor_id}, {"_id": 0})
    if not instructor:
        raise HTTPException(status_code=404, detail="Instruktor nenalezen")
    return Instructor(**_instructor_response(instructor))

@api_router.post("/instructors", response_model=Instructor)
async def create_instructor(data: InstructorCreate, user: User = Depends(get_admin_user)):
    """Create a new instructor"""
    instructor_id = f"inst_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    payload = data.model_dump()
    pin = payload.pop("pin", None)
    instructor = {
        "instructor_id": instructor_id,
        **payload,
        "pin": hash_password(pin) if pin else None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    }

    await db.instructors.insert_one(dict(instructor))
    instructor['created_at'] = now
    instructor['updated_at'] = now
    return Instructor(**_instructor_response(instructor))

@api_router.put("/instructors/{instructor_id}", response_model=Instructor)
async def update_instructor(instructor_id: str, data: InstructorCreate, user: User = Depends(get_admin_user)):
    """Update an instructor.

    An empty PIN field means "leave the current PIN alone" — the form never
    receives the stored PIN back, so submitting it must not wipe the login.
    """
    instructor = await db.instructors.find_one({"instructor_id": instructor_id}, {"_id": 0})
    if not instructor:
        raise HTTPException(status_code=404, detail="Instruktor nenalezen")

    now = datetime.now(timezone.utc)
    payload = data.model_dump()
    pin = payload.pop("pin", None)
    update_data = {**payload, "updated_at": now.isoformat()}
    if pin:
        update_data["pin"] = hash_password(pin)

    await db.instructors.update_one(
        {"instructor_id": instructor_id},
        {"$set": update_data}
    )

    updated = await db.instructors.find_one({"instructor_id": instructor_id}, {"_id": 0})
    return Instructor(**_instructor_response(updated))

@api_router.delete("/instructors/{instructor_id}")
async def delete_instructor(instructor_id: str, user: User = Depends(get_admin_user)):
    """Delete an instructor"""
    result = await db.instructors.delete_one({"instructor_id": instructor_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Instruktor nenalezen")
    return {"message": "Instruktor smazán"}

# ======================== LOGBOOK (KNIHA JÍZD) ROUTES ========================

@api_router.get("/logbook", response_model=List[LogbookEntry])
async def get_logbook_entries(
    vehicle_id: Optional[str] = None,
    instructor_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(1000, ge=1, le=20000),
    user: User = Depends(get_current_user)
):
    """Get logbook entries with optional filters"""
    query = {}
    if vehicle_id:
        query["vehicle_id"] = vehicle_id
    if instructor_id:
        query["instructor_id"] = instructor_id
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    
    entries = await db.logbook.find(query, {"_id": 0}).sort("date", -1).to_list(limit)

    for entry in entries:
        parse_datetime_field(entry, "created_at")
    await enrich_many(entries, with_instructor=True)

    return entries

@api_router.post("/logbook", response_model=LogbookEntry)
async def create_logbook_entry(data: LogbookEntryCreate, user: User = Depends(get_current_user)):
    """Create a new logbook entry"""
    entry_id = f"log_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    
    distance = data.end_odometer - data.start_odometer
    
    entry = {
        "entry_id": entry_id,
        **data.model_dump(),
        "distance": distance,
        "gps_source": False,
        "created_at": now.isoformat()
    }
    
    await db.logbook.insert_one(entry)
    
    # Update vehicle odometer
    await db.vehicles.update_one(
        {"vehicle_id": data.vehicle_id},
        {"$set": {"odometer": data.end_odometer, "updated_at": now.isoformat()}}
    )
    
    entry['created_at'] = now
    
    await enrich_vehicle_info(entry)
    await enrich_instructor_name(entry)
    
    return LogbookEntry(**entry)

@api_router.delete("/logbook/{entry_id}")
async def delete_logbook_entry(entry_id: str, user: User = Depends(get_current_user)):
    """Delete a logbook entry"""
    result = await db.logbook.delete_one({"entry_id": entry_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Záznam nenalezen")
    return {"message": "Záznam smazán"}

# ======================== FUEL ENTRY ROUTES ========================

@api_router.get("/fuel", response_model=List[FuelEntry])
async def get_fuel_entries(
    vehicle_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Get fuel entries with optional filters"""
    query = {}
    if vehicle_id:
        query["vehicle_id"] = vehicle_id
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    
    entries = await db.fuel_entries.find(query, {"_id": 0}).sort("date", -1).to_list(1000)

    for entry in entries:
        parse_datetime_field(entry, "created_at")
    await enrich_many(entries)

    return entries

@api_router.post("/fuel", response_model=FuelEntry)
async def create_fuel_entry(data: FuelEntryCreate, user: User = Depends(get_current_user)):
    """Create a new fuel entry"""
    fuel_id = f"fuel_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    
    entry = {
        "fuel_id": fuel_id,
        **data.model_dump(),
        "created_at": now.isoformat()
    }
    
    await db.fuel_entries.insert_one(entry)
    
    # Update vehicle odometer
    await db.vehicles.update_one(
        {"vehicle_id": data.vehicle_id},
        {"$set": {"odometer": data.odometer, "updated_at": now.isoformat()}}
    )
    
    entry['created_at'] = now
    
    await enrich_vehicle_info(entry)
    
    return FuelEntry(**entry)

# Public endpoint for QR fuel entry
@api_router.post("/public/fuel")
async def create_public_fuel_entry(data: FuelEntryCreate):
    """Create fuel entry via QR code (public endpoint)"""
    vehicle = await db.vehicles.find_one({"vehicle_id": data.vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    fuel_id = f"fuel_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    
    entry = {
        "fuel_id": fuel_id,
        **data.model_dump(),
        "created_at": now.isoformat()
    }
    
    await db.fuel_entries.insert_one(entry)
    
    await db.vehicles.update_one(
        {"vehicle_id": data.vehicle_id},
        {"$set": {"odometer": data.odometer, "updated_at": now.isoformat()}}
    )
    
    return {"message": "Tankování úspěšně zaznamenáno", "fuel_id": fuel_id}

# ======================== DAMAGE REPORT ROUTES ========================

@api_router.get("/damages", response_model=List[DamageReport])
async def get_damage_reports(
    vehicle_id: Optional[str] = None,
    status: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Get damage reports with optional filters"""
    query = {}
    if vehicle_id:
        query["vehicle_id"] = vehicle_id
    if status:
        query["status"] = status
    
    reports = await db.damage_reports.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    for report in reports:
        parse_datetime_field(report, "created_at")
        parse_datetime_field(report, "resolved_at")
    await enrich_many(reports)

    return reports

@api_router.post("/damages", response_model=DamageReport)
async def create_damage_report(data: DamageReportCreate, user: User = Depends(get_current_user)):
    """Create a new damage report"""
    damage_id = f"dmg_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    
    report = {
        "damage_id": damage_id,
        **data.model_dump(),
        "status": "otevřeno",
        "created_at": now.isoformat(),
        "resolved_at": None
    }
    
    await db.damage_reports.insert_one(report)
    report['created_at'] = now
    
    await enrich_vehicle_info(report)
    
    # Send email notification
    asyncio.create_task(send_damage_notification(report, report.get("vehicle_info", "")))
    
    return DamageReport(**report)

@api_router.put("/damages/{damage_id}/status")
async def update_damage_status(damage_id: str, status: str, user: User = Depends(get_current_user)):
    """Update damage report status"""
    report = await db.damage_reports.find_one({"damage_id": damage_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Hlášení nenalezeno")
    
    update_data = {"status": status}
    if status == "vyřešeno":
        update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.damage_reports.update_one(
        {"damage_id": damage_id},
        {"$set": update_data}
    )
    
    return {"message": "Status aktualizován"}

# Public endpoint for QR damage report
@api_router.post("/public/damages")
async def create_public_damage_report(data: DamageReportCreate):
    """Create damage report via QR code (public endpoint)"""
    vehicle = await db.vehicles.find_one({"vehicle_id": data.vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    damage_id = f"dmg_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    
    report = {
        "damage_id": damage_id,
        **data.model_dump(),
        "status": "otevřeno",
        "created_at": now.isoformat(),
        "resolved_at": None
    }
    
    await db.damage_reports.insert_one(report)
    
    # Send email notification
    vehicle_info = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    asyncio.create_task(send_damage_notification(report, vehicle_info))
    
    return {"message": "Poškození úspěšně nahlášeno", "damage_id": damage_id}

# ======================== HANDOVER PROTOCOL ROUTES ========================

@api_router.get("/handovers", response_model=List[HandoverProtocol])
async def get_handover_protocols(
    vehicle_id: Optional[str] = None,
    instructor_id: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Get handover protocols with optional filters"""
    query = {}
    if vehicle_id:
        query["vehicle_id"] = vehicle_id
    if instructor_id:
        query["instructor_id"] = instructor_id
    
    protocols = await db.handover_protocols.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    for protocol in protocols:
        parse_datetime_field(protocol, "created_at")
    await enrich_many(protocols, with_instructor=True)

    return protocols

@api_router.post("/handovers", response_model=HandoverProtocol)
async def create_handover_protocol(data: HandoverProtocolCreate, user: User = Depends(get_current_user)):
    """Create a new handover protocol"""
    handover_id = f"hand_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    
    protocol = {
        "handover_id": handover_id,
        **data.model_dump(),
        "created_at": now.isoformat()
    }
    
    await db.handover_protocols.insert_one(protocol)
    
    # Update vehicle odometer
    await db.vehicles.update_one(
        {"vehicle_id": data.vehicle_id},
        {"$set": {"odometer": data.odometer, "updated_at": now.isoformat()}}
    )
    
    protocol['created_at'] = now
    
    await enrich_vehicle_info(protocol)
    await enrich_instructor_name(protocol)
    
    return HandoverProtocol(**protocol)

# ======================== QR HANDOVER ROUTES ========================

@api_router.get("/qr-handovers")
async def get_qr_handovers(
    vehicle_id: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Get QR handover protocols with optional filters"""
    query = {}
    if vehicle_id:
        query["vehicle_id"] = vehicle_id
    
    handovers = await db.qr_handovers.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)

    for h in handovers:
        parse_datetime_field(h, "created_at")
    await enrich_many(handovers)

    return handovers

@api_router.get("/qr-handovers/{qr_handover_id}")
async def get_qr_handover(qr_handover_id: str, user: User = Depends(get_current_user)):
    """Get a single QR handover protocol"""
    handover = await db.qr_handovers.find_one({"qr_handover_id": qr_handover_id}, {"_id": 0})
    if not handover:
        raise HTTPException(status_code=404, detail="Předávací protokol nenalezen")
    
    parse_datetime_field(handover, "created_at")
    await enrich_vehicle_info(handover)
    
    return handover

# Public endpoint for QR handover submission
def _validate_handover_photos(photos: list):
    """Validate all 6 required photo types are present."""
    required = {"front", "rear", "left", "right", "interior", "dashboard"}
    provided = {p.photo_type for p in photos}
    missing = required - provided
    if missing:
        raise HTTPException(status_code=400, detail=f"Chybí požadované fotografie: {', '.join(missing)}")


def _validate_fluid_checks(fluid_checks: FluidChecks):
    """Validate all fluid checks are confirmed."""
    if not all([
        fluid_checks.engine_oil,
        fluid_checks.coolant,
        fluid_checks.brake_fluid,
        fluid_checks.windshield_washer,
        fluid_checks.other_fluids
    ]):
        raise HTTPException(status_code=400, detail="Všechny provozní kapaliny musí být zkontrolovány")


@api_router.post("/public/qr-handover")
async def create_public_qr_handover(data: QRHandoverCreate):
    """Create QR handover protocol via QR code (public endpoint for mobile)"""
    vehicle = await db.vehicles.find_one({"vehicle_id": data.vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    _validate_handover_photos(data.photos)
    _validate_fluid_checks(data.fluid_checks)

    qr_handover_id = f"qrh_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    handover = {
        "qr_handover_id": qr_handover_id,
        "vehicle_id": data.vehicle_id,
        "handler_name": data.handler_name,
        "handler_type": data.handler_type,
        "odometer": data.odometer,
        "fuel_level": data.fuel_level,
        "fluid_checks": data.fluid_checks.model_dump(),
        "photos": [p.model_dump() for p in data.photos],
        "notes": data.notes,
        "created_at": now.isoformat()
    }

    await db.qr_handovers.insert_one(handover)

    await db.vehicles.update_one(
        {"vehicle_id": data.vehicle_id},
        {"$set": {"odometer": data.odometer, "updated_at": now.isoformat()}}
    )

    return {
        "message": "Předávací protokol úspěšně vytvořen",
        "qr_handover_id": qr_handover_id,
        "vehicle": f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    }

# ======================== GPS TRACKER ROUTES ========================

@api_router.get("/gps/trips", response_model=List[GPSTrip])
async def get_gps_trips(
    vehicle_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    source: Optional[str] = None,
    include_duplicates: bool = False,
    include_route: bool = False,
    limit: int = Query(1000, ge=1, le=20000),
    user: User = Depends(get_current_user)
):
    """GPS trips with optional filters.

    `date_from`/`date_to` used to be accepted and then ignored, so every client
    received the full history no matter what period it asked for. They now
    filter on the local calendar date, like every other report.

    Route points are omitted unless `include_route=true`; a long history of
    trips otherwise transfers megabytes of coordinates the list view never
    shows.
    """
    trip_list = await trips_service.get_trips(
        db,
        vehicle_id=vehicle_id,
        date_from=date_from,
        date_to=date_to,
        sources=_parse_source_filter(source),
        include_duplicates=include_duplicates,
        include_manual=False,
        limit=limit,
    )
    await trips_service.resolve_trip_instructors(db, trip_list)

    trip_ids = [t["trip_id"] for t in trip_list]
    routes = {}
    if include_route and trip_ids:
        docs = await db.gps_trips.find(
            {"trip_id": {"$in": trip_ids}}, {"_id": 0, "trip_id": 1, "route_points": 1}
        ).to_list(len(trip_ids) + 10)
        routes = {d["trip_id"]: d.get("route_points", []) for d in docs}

    result = []
    for trip in sorted(trip_list, key=lambda t: t["start_time"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        result.append({
            "trip_id": trip["trip_id"],
            "vehicle_id": trip["vehicle_id"],
            "vehicle_info": trip.get("vehicle_info"),
            "source": trip["source"],
            "start_time": trip["start_time"],
            "end_time": trip["end_time"],
            "start_location": trip["start_location"],
            "end_location": trip["end_location"],
            "route_points": routes.get(trip["trip_id"], []),
            "distance": trip["distance_m"],
            "max_speed": trip["max_speed"],
            "avg_speed": trip["avg_speed"],
            "synced_to_logbook": trip["synced_to_logbook"],
            "duplicate_of": trip.get("duplicate_of"),
            "created_at": trip["start_time"] or datetime.now(timezone.utc),
        })
    return result


@api_router.get("/gps/trips/{trip_id}/route")
async def get_gps_trip_route(
    trip_id: str,
    max_points: int = Query(2000, ge=2, le=50000),
    user: User = Depends(get_current_user),
):
    """Route of a single trip, down-sampled for map display.

    Down-sampling only affects what is sent to the browser — the stored GPS
    history is never modified or trimmed.
    """
    trip = await db.gps_trips.find_one({"trip_id": trip_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="GPS záznam nenalezen")

    points = trip.get("route_points") or []
    total = len(points)
    if total > max_points:
        step = total / float(max_points)
        sampled = [points[int(i * step)] for i in range(max_points)]
        if sampled[-1] is not points[-1]:
            sampled[-1] = points[-1]
        points = sampled

    # Odometer and fuel level at both ends of the drive, so the trip list can
    # answer "what did the car show when this drive started / finished?"
    start_at = trips_service.to_utc(trip.get("start_time"))
    end_at = trips_service.to_utc(trip.get("end_time"))
    state_start = state_end = None
    if start_at:
        readings = await vehicle_state.collect_readings(
            db, trip["vehicle_id"], date_to=trips_service.local_date_of(end_at or start_at)
        )
        state_start = vehicle_state.state_at(readings, start_at)
        if end_at:
            state_end = vehicle_state.state_at(readings, end_at)

    def brief(state):
        if not state:
            return None
        return {
            "odometer_km": state["odometer_km"],
            "odometer_is_estimate": state["odometer_is_estimate"],
            "odometer_source_label": state["odometer_source_label"],
            "fuel_level_percent": state["fuel_level_percent"],
            "fuel_source_label": state["fuel_source_label"],
        }

    return {
        "trip_id": trip_id,
        "source": trips_service.trip_source(trip),
        "points": points,
        "total_points": total,
        "downsampled": total > len(points),
        "state_start": brief(state_start),
        "state_end": brief(state_end),
    }

# Sample Czech locations for driving school
_MOCK_LOCATIONS = [
    {"lat": 50.0755, "lng": 14.4378, "address": "Praha, Václavské náměstí"},
    {"lat": 50.0880, "lng": 14.4208, "address": "Praha, Letná"},
    {"lat": 50.0663, "lng": 14.3782, "address": "Praha, Smíchov"},
    {"lat": 50.1010, "lng": 14.4000, "address": "Praha, Kobylisy"},
    {"lat": 50.0500, "lng": 14.4600, "address": "Praha, Vršovice"},
    {"lat": 50.0800, "lng": 14.5000, "address": "Praha, Žižkov"},
]


def _generate_route_points(start_loc: dict, end_loc: dict, start_time: datetime, duration_minutes: int) -> list:
    """Generate interpolated route points between two locations."""
    num_points = secrets.randbelow(21) + 10
    points = []
    for i in range(num_points):
        progress = i / num_points
        lat = start_loc["lat"] + (end_loc["lat"] - start_loc["lat"]) * progress + (secrets.randbelow(1001) - 500) / 100000
        lng = start_loc["lng"] + (end_loc["lng"] - start_loc["lng"]) * progress + (secrets.randbelow(1001) - 500) / 100000
        point_time = start_time + timedelta(minutes=int(duration_minutes * progress))
        points.append({"lat": lat, "lng": lng, "timestamp": point_time.isoformat()})
    return points


def _generate_mock_trip(vehicle_id: str, trip_date: datetime, trip_num: int, now: datetime) -> dict:
    """Generate a single mock GPS trip dict."""
    start_hour = 8 + trip_num * 3
    start_time = trip_date.replace(hour=start_hour, minute=secrets.randbelow(31))
    duration_minutes = secrets.randbelow(61) + 30
    end_time = start_time + timedelta(minutes=duration_minutes)

    start_loc = secrets.choice(_MOCK_LOCATIONS)
    end_loc = secrets.choice([loc for loc in _MOCK_LOCATIONS if loc != start_loc])
    distance = secrets.randbelow(20001) + 5000

    return {
        "trip_id": f"gps_{uuid.uuid4().hex[:12]}",
        "vehicle_id": vehicle_id,
        # Tagged as mock so reports never mix demo kilometres with real ones.
        "source": trips_service.SOURCE_MOCK,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "start_location": start_loc,
        "end_location": end_loc,
        "route_points": _generate_route_points(start_loc, end_loc, start_time, duration_minutes),
        "distance": distance,
        "max_speed": secrets.randbelow(31) + 50,
        "avg_speed": secrets.randbelow(21) + 25,
        "synced_to_logbook": False,
        "duplicate_of": None,
        "created_at": now.isoformat()
    }


def _require_mock_data_enabled():
    """Mock generators write into the same collections as real tracker data.

    They stay disabled unless ALLOW_MOCK_DATA is set, so a demo button cannot
    inject fabricated kilometres into a production logbook.
    """
    if not settings.allow_mock_data:
        raise HTTPException(
            status_code=403,
            detail="Generování ukázkových dat je v tomto prostředí vypnuté (ALLOW_MOCK_DATA).",
        )


@api_router.post("/gps/import-mock")
async def import_mock_gps_data(vehicle_id: str, user: User = Depends(get_admin_user)):
    """Generate mock GPS data for a vehicle (development aid, disabled in production)."""
    _require_mock_data_enabled()
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    now = datetime.now(timezone.utc)
    trips_created = []

    for day_offset in range(7):
        num_trips = secrets.randbelow(3) + 1
        trip_date = now - timedelta(days=day_offset)
        for trip_num in range(num_trips):
            trip = _generate_mock_trip(vehicle_id, trip_date, trip_num, now)
            await db.gps_trips.insert_one(trip)
            trips_created.append(trip["trip_id"])

    return {"message": f"Importováno {len(trips_created)} GPS záznamů", "trip_ids": trips_created}

def _parse_trip_times(trip: dict) -> tuple:
    """Parse start_time and end_time from a GPS trip document."""
    st = trip["start_time"]
    et = trip["end_time"]
    start_time = datetime.fromisoformat(st) if isinstance(st, str) else st
    end_time = datetime.fromisoformat(et) if isinstance(et, str) else et
    return start_time, end_time


@api_router.post("/gps/trips/{trip_id}/sync-to-logbook")
async def sync_trip_to_logbook(trip_id: str, user: User = Depends(get_current_user)):
    """Sync a GPS trip to the logbook"""
    trip = await db.gps_trips.find_one({"trip_id": trip_id}, {"_id": 0})
    if not trip:
        raise HTTPException(status_code=404, detail="GPS záznam nenalezen")
    if trip.get("synced_to_logbook"):
        raise HTTPException(status_code=400, detail="Záznam již byl synchronizován")
    if trip.get("duplicate_of"):
        raise HTTPException(
            status_code=400,
            detail="Tato jízda je označena jako duplicita již zaznamenané jízdy a nelze ji zapsat do knihy jízd.",
        )

    vehicle = await db.vehicles.find_one({"vehicle_id": trip["vehicle_id"]}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    start_time, end_time = _parse_trip_times(trip)
    now = datetime.now(timezone.utc)
    # Round rather than truncate: flooring dropped up to a kilometre per trip
    # from the odometer on every sync.
    distance_km = int(round((trip.get("distance") or 0) / 1000))
    start_odometer = vehicle.get("odometer", 0)
    end_odometer = start_odometer + distance_km

    source = trips_service.trip_source(trip)
    local_start = start_time.astimezone(trips_service.REPORT_TZ) if start_time.tzinfo else start_time
    local_end = end_time.astimezone(trips_service.REPORT_TZ) if end_time.tzinfo else end_time
    start_address = (trip.get("start_location") or {}).get("address") or "GPS"
    end_address = (trip.get("end_location") or {}).get("address") or "GPS"

    logbook_entry = {
        "entry_id": f"log_{uuid.uuid4().hex[:12]}",
        "vehicle_id": trip["vehicle_id"],
        "instructor_id": vehicle.get("assigned_instructor_id"),
        "date": local_start.strftime("%Y-%m-%d"),
        "start_time": local_start.strftime("%H:%M"),
        "end_time": local_end.strftime("%H:%M"),
        "start_location": start_address,
        "end_location": end_address,
        "route_description": f"{start_address} → {end_address}",
        "start_odometer": start_odometer,
        "end_odometer": end_odometer,
        "distance": distance_km,
        "purpose": "výcvik",
        "notes": f"Import z {source} (max. rychlost: {trip.get('max_speed', 0)} km/h, "
                 f"prům. rychlost: {trip.get('avg_speed', 0)} km/h)",
        # Marks this row as a projection of a trip, so reports count the trip
        # itself and not both. `source_trip_id` keeps the link explicit.
        "gps_source": True,
        "source": source,
        "source_trip_id": trip_id,
        "created_at": now.isoformat()
    }

    await db.logbook.insert_one(logbook_entry)
    await db.gps_trips.update_one({"trip_id": trip_id}, {"$set": {"synced_to_logbook": True}})
    await db.vehicles.update_one(
        {"vehicle_id": trip["vehicle_id"]},
        {"$set": {"odometer": end_odometer, "updated_at": now.isoformat()}}
    )

    return {"message": "Záznam synchronizován do knihy jízd", "entry_id": logbook_entry["entry_id"]}

# ======================== REPORTS & ANALYTICS ========================

def _parse_source_filter(source: Optional[str]) -> Optional[List[str]]:
    """Turn a `source=` query parameter into a list of trip sources.

    Reports include every real source by default. Filtering by source is
    possible but never the default, so a drive imported from Ruhavik counts
    exactly like one recorded by a tracker.
    """
    if not source or source.strip().lower() in ("", "all", "vse", "vše"):
        return None
    requested = [part.strip().lower() for part in source.split(",") if part.strip()]
    unknown = [part for part in requested if part not in trips_service.ALL_SOURCES]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Neznámý zdroj jízd: {', '.join(unknown)}. "
                   f"Povolené hodnoty: {', '.join(trips_service.ALL_SOURCES)}.",
        )
    return requested


async def _load_report_trips(
    vehicle_id: Optional[str] = None,
    instructor_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    source: Optional[str] = None,
    include_duplicates: bool = False,
) -> List[dict]:
    """Fetch trips for a report, enriched with vehicle and instructor names.

    Single entry point for every report so the same period can never produce a
    different number of trips on two different screens.
    """
    trip_list = await trips_service.get_trips(
        db,
        vehicle_id=vehicle_id,
        date_from=date_from,
        date_to=date_to,
        sources=_parse_source_filter(source),
        include_duplicates=include_duplicates,
    )
    await trips_service.resolve_trip_instructors(db, trip_list)
    if instructor_id:
        trip_list = [t for t in trip_list if t.get("instructor_id") == instructor_id]
    return trip_list


def _serialize_trip(trip: dict) -> dict:
    """JSON-safe view of a normalised trip."""
    out = dict(trip)
    for field in ("start_time", "end_time"):
        value = out.get(field)
        out[field] = value.isoformat() if isinstance(value, datetime) else value
    return out


@api_router.get("/reports/dashboard")
async def get_dashboard_stats(user: User = Depends(get_current_user)):
    """Dashboard statistics.

    Trip figures come from the unified trip layer, so tracker-recorded,
    Ruhavik-imported and hand-written drives are all counted.
    """
    now = datetime.now(timezone.utc)
    month_start = now.astimezone(trips_service.REPORT_TZ).replace(day=1).date().isoformat()
    week_ago = (now - timedelta(days=7)).astimezone(trips_service.REPORT_TZ).date().isoformat()
    today = now.astimezone(trips_service.REPORT_TZ).date().isoformat()

    total_vehicles = await db.vehicles.count_documents({})
    total_instructors = await db.instructors.count_documents({})

    month_trips = await _load_report_trips(date_from=month_start, date_to=today)
    month_summary = trips_service.summarize(month_trips)
    recent_trips = sum(1 for t in month_trips if t["date"] and t["date"] >= week_ago)

    fuel_entries = await db.fuel_entries.find(
        {"date": {"$gte": month_start}}, {"_id": 0, "total_price": 1}
    ).to_list(10000)
    total_fuel_cost_month = sum(entry.get("total_price", 0) or 0 for entry in fuel_entries)

    open_damages = await db.damage_reports.count_documents({"status": {"$ne": "vyřešeno"}})
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(1000)

    return {
        "total_vehicles": total_vehicles,
        "total_instructors": total_instructors,
        "total_km_month": round(month_summary["total_distance_km"]),
        "total_fuel_cost_month": round(total_fuel_cost_month, 2),
        "open_damages": open_damages,
        "recent_trips": recent_trips,
        "trips_month": month_summary["total_trips"],
        "km_month_by_source": month_summary["by_source"],
        "vehicles": vehicles,
    }


@api_router.get("/reports/km-stats")
async def get_km_statistics(
    date_from: str,
    date_to: str,
    vehicle_id: Optional[str] = None,
    instructor_id: Optional[str] = None,
    source: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Kilometre statistics for a period, across every trip source."""
    trip_list = await _load_report_trips(
        vehicle_id=vehicle_id,
        instructor_id=instructor_id,
        date_from=date_from,
        date_to=date_to,
        source=source,
    )
    summary = trips_service.summarize(trip_list)

    # `vehicle_stats` keeps its historical keyed-object shape for the existing
    # frontend; `by_source` is additive.
    vehicle_stats = {
        bucket["vehicle_id"]: {
            "total_km": bucket["distance_km"],
            "trips": bucket["trips"],
            "name": bucket.get("vehicle_info"),
            "sources": bucket.get("sources", {}),
        }
        for bucket in summary["by_vehicle"]
    }

    return {
        "total_km": summary["total_distance_km"],
        "total_trips": summary["total_trips"],
        "avg_km_per_day": summary["avg_km_per_day"],
        "daily_stats": [{"date": d["date"], "km": d["km"]} for d in summary["daily"]],
        "vehicle_stats": vehicle_stats,
        "by_source": summary["by_source"],
        "instructor_stats": summary["by_instructor"],
    }


@api_router.get("/reports/trips")
async def get_trip_report(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    vehicle_id: Optional[str] = None,
    instructor_id: Optional[str] = None,
    source: Optional[str] = None,
    include_duplicates: bool = False,
    user: User = Depends(get_current_user),
):
    """Unified trip report: every drive from every source, plus totals."""
    trip_list = await _load_report_trips(
        vehicle_id=vehicle_id,
        instructor_id=instructor_id,
        date_from=date_from,
        date_to=date_to,
        source=source,
        include_duplicates=include_duplicates,
    )
    return {
        "trips": [_serialize_trip(t) for t in trip_list],
        "summary": trips_service.summarize(trip_list),
        "filters": {
            "date_from": date_from, "date_to": date_to, "vehicle_id": vehicle_id,
            "instructor_id": instructor_id, "source": source,
            "include_duplicates": include_duplicates,
        },
    }


@api_router.get("/reports/trips/export-csv")
async def export_trip_report_csv(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    vehicle_id: Optional[str] = None,
    instructor_id: Optional[str] = None,
    source: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """CSV export of the unified trip report (semicolon separated, UTF-8 BOM)."""
    trip_list = await _load_report_trips(
        vehicle_id=vehicle_id, instructor_id=instructor_id,
        date_from=date_from, date_to=date_to, source=source,
    )

    buffer = io.StringIO()
    writer = csv_module.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow([
        "Datum", "Zacatek", "Konec", "Vozidlo", "Ucitel", "Odkud", "Kam",
        "Vzdalenost (km)", "Doba (min)", "Max. rychlost", "Zdroj",
    ])
    for trip in trip_list:
        start = trip.get("start_time")
        end = trip.get("end_time")
        writer.writerow([
            trip.get("date") or "",
            start.astimezone(trips_service.REPORT_TZ).strftime("%H:%M") if start else "",
            end.astimezone(trips_service.REPORT_TZ).strftime("%H:%M") if end else "",
            trip.get("vehicle_info") or trip.get("vehicle_id") or "",
            trip.get("instructor_name") or "",
            trip.get("start_address") or "",
            trip.get("end_address") or "",
            f"{trip.get('distance_km', 0):.2f}".replace(".", ","),
            trip.get("duration_min") or 0,
            trip.get("max_speed") or 0,
            trip.get("source") or "",
        ])

    summary = trips_service.summarize(trip_list)
    writer.writerow([])
    writer.writerow(["Celkem jizd", summary["total_trips"]])
    writer.writerow(["Celkem km", f"{summary['total_distance_km']:.1f}".replace(".", ",")])
    for src, bucket in sorted(summary["by_source"].items()):
        writer.writerow([f"  z toho {src}", bucket["trips"], f"{bucket['distance_km']:.1f}".replace(".", ",")])

    payload = "\ufeff" + buffer.getvalue()
    filename = f"jizdy-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        io.BytesIO(payload.encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.get("/reports/vehicle/{vehicle_id}")
async def get_vehicle_report(
    vehicle_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    source: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """Per-vehicle statistics across every trip source."""
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    trip_list = await _load_report_trips(
        vehicle_id=vehicle_id, date_from=date_from, date_to=date_to, source=source
    )
    summary = trips_service.summarize(trip_list)
    return {
        "vehicle_id": vehicle_id,
        "vehicle_info": f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})",
        "odometer": vehicle.get("odometer", 0),
        "summary": summary,
        "trips": [_serialize_trip(t) for t in trip_list],
    }


@api_router.get("/reports/instructor/{instructor_id}")
async def get_instructor_report(
    instructor_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    source: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """Per-instructor statistics.

    GPS and Ruhavik drives have no instructor of their own, so they are
    attributed through the instructor assigned to the vehicle.
    """
    instructor = await db.instructors.find_one({"instructor_id": instructor_id}, {"_id": 0})
    if not instructor:
        raise HTTPException(status_code=404, detail="Instruktor nenalezen")

    trip_list = await _load_report_trips(
        instructor_id=instructor_id, date_from=date_from, date_to=date_to, source=source
    )
    return {
        "instructor_id": instructor_id,
        "instructor_name": instructor.get("name"),
        "summary": trips_service.summarize(trip_list),
        "trips": [_serialize_trip(t) for t in trip_list],
    }


def _aggregate_fuel_per_vehicle(fuel_entries: list, vehicle_map: dict) -> dict:
    """Aggregate fuel entries per vehicle."""
    vehicle_fuel_data = {}
    for entry in fuel_entries:
        vid = entry["vehicle_id"]
        if vid not in vehicle_fuel_data:
            v = vehicle_map.get(vid, {})
            vehicle_fuel_data[vid] = {
                "vehicle_id": vid,
                "vehicle_info": f"{v.get('brand', '?')} {v.get('model', '?')} ({v.get('registration_plate', '?')})",
                "entries": [],
                "total_liters": 0,
                "total_cost": 0,
                "odometer_readings": [],
            }
        vd = vehicle_fuel_data[vid]
        liters = entry.get("amount_liters", entry.get("amount", 0))
        cost = entry.get("total_price", entry.get("price", 0))
        odo = entry.get("odometer", 0)
        vd["entries"].append({"date": entry.get("date", ""), "liters": liters, "cost": cost, "odometer": odo})
        vd["total_liters"] += liters
        vd["total_cost"] += cost
        if odo > 0:
            vd["odometer_readings"].append(odo)
    return vehicle_fuel_data


def _compute_vehicle_fuel_stats(vehicle_fuel_data: dict) -> tuple:
    """Compute per-vehicle fuel stats and totals. Returns (vehicle_stats, totals)."""
    vehicle_stats = []
    total_liters = total_cost = total_km = 0
    for vid, vd in vehicle_fuel_data.items():
        readings = sorted(vd["odometer_readings"])
        km_driven = (readings[-1] - readings[0]) if len(readings) >= 2 else 0
        consumption = round((vd["total_liters"] / km_driven) * 100, 2) if km_driven > 0 else 0
        cost_per_km = round(vd["total_cost"] / km_driven, 2) if km_driven > 0 else 0
        total_liters += vd["total_liters"]
        total_cost += vd["total_cost"]
        total_km += km_driven
        monthly = {}
        for e in vd["entries"]:
            month = e["date"][:7] if e["date"] else "?"
            if month not in monthly:
                monthly[month] = {"liters": 0, "cost": 0}
            monthly[month]["liters"] += e["liters"]
            monthly[month]["cost"] += e["cost"]
        vehicle_stats.append({
            "vehicle_id": vid, "vehicle_info": vd["vehicle_info"],
            "total_liters": round(vd["total_liters"], 2), "total_cost": round(vd["total_cost"], 2),
            "km_driven": km_driven, "consumption_per_100km": consumption,
            "cost_per_km": cost_per_km, "fill_count": len(vd["entries"]),
            "monthly_trend": [{"month": k, **v} for k, v in sorted(monthly.items())],
        })
    return vehicle_stats, {"total_liters": round(total_liters, 2), "total_cost": round(total_cost, 2), "total_km": total_km}


@api_router.get("/reports/fuel-analytics")
async def fuel_consumption_analytics(
    vehicle_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Fuel consumption analytics - l/100km, cost, trends per vehicle."""
    fuel_query = {}
    if vehicle_id:
        fuel_query["vehicle_id"] = vehicle_id
    if date_from or date_to:
        fuel_query["date"] = {}
        if date_from:
            fuel_query["date"]["$gte"] = date_from
        if date_to:
            fuel_query["date"]["$lte"] = date_to

    fuel_entries = await db.fuel_entries.find(fuel_query, {"_id": 0}).sort("date", 1).to_list(10000)
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(100)
    vehicle_map = {v["vehicle_id"]: v for v in vehicles}

    vehicle_fuel_data = _aggregate_fuel_per_vehicle(fuel_entries, vehicle_map)
    vehicle_stats, totals = _compute_vehicle_fuel_stats(vehicle_fuel_data)
    avg_consumption = round((totals["total_liters"] / totals["total_km"]) * 100, 2) if totals["total_km"] > 0 else 0

    return {
        "summary": {**totals, "avg_consumption_per_100km": avg_consumption, "vehicle_count": len(vehicle_stats)},
        "vehicle_stats": vehicle_stats,
    }

# ======================== PDF EXPORT ========================

def _build_logbook_pdf(entries: list, date_from: str, date_to: str) -> io.BytesIO:
    """Generate a Czech-format logbook PDF from entries."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCZ", parent=styles["Title"], fontSize=16, spaceAfter=6)
    subtitle_style = ParagraphStyle("SubCZ", parent=styles["Normal"], fontSize=10, textColor=colors.grey, spaceAfter=12)
    cell_style = ParagraphStyle("CellCZ", parent=styles["Normal"], fontSize=7, leading=9)
    header_style = ParagraphStyle("HeaderCZ", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.white)

    elements = []
    elements.append(Paragraph("Kniha jizd - Autoskola", title_style))
    period = f"Obdobi: {date_from or 'neuvedeno'} az {date_to or 'neuvedeno'}"
    elements.append(Paragraph(period, subtitle_style))
    elements.append(Spacer(1, 4*mm))

    headers = ["Datum", "Cas", "Vozidlo", "Ridic", "Odkud", "Kam", "Zac. km", "Kon. km", "Vzd.", "Ucel", "Zdroj"]
    header_row = [Paragraph(h, header_style) for h in headers]

    data = [header_row]
    total_km = 0
    for e in entries:
        distance = e.get("distance", 0)
        total_km += distance
        source = e.get("source_label") or ("GPS" if e.get("gps_source") else "Man.")
        row = [
            Paragraph(e.get("date", ""), cell_style),
            Paragraph(f"{e.get('start_time', '')}-{e.get('end_time', '')}", cell_style),
            Paragraph(e.get("vehicle_info", ""), cell_style),
            Paragraph(e.get("instructor_name", "-"), cell_style),
            Paragraph(e.get("start_location", ""), cell_style),
            Paragraph(e.get("end_location", ""), cell_style),
            Paragraph(str(e.get("start_odometer", "")), cell_style),
            Paragraph(str(e.get("end_odometer", "")), cell_style),
            Paragraph(f"{distance} km", cell_style),
            Paragraph(e.get("purpose", ""), cell_style),
            Paragraph(source, cell_style),
        ]
        data.append(row)

    # Summary row
    summary_row = [Paragraph("", cell_style)] * 8 + [
        Paragraph(f"{total_km} km", ParagraphStyle("BoldCell", parent=cell_style, fontName="Helvetica-Bold")),
        Paragraph("Celkem", cell_style),
        Paragraph("", cell_style),
    ]
    data.append(summary_row)

    col_widths = [22*mm, 22*mm, 40*mm, 28*mm, 35*mm, 35*mm, 18*mm, 18*mm, 18*mm, 20*mm, 14*mm]

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002FA7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (6, 1), (8, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E4E4E7")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F4F4F5")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F4F4F5")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(table)

    elements.append(Spacer(1, 8*mm))
    footer_text = f"Vygenerovano: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC | Celkem zaznamu: {len(entries)} | Celkem km: {total_km}"
    elements.append(Paragraph(footer_text, subtitle_style))

    doc.build(elements)
    buf.seek(0)
    return buf


_SOURCE_LABELS = {
    trips_service.SOURCE_TELTONIKA: "GPS",
    trips_service.SOURCE_RUHAVIK: "Ruhavik",
    trips_service.SOURCE_MANUAL: "Man.",
    trips_service.SOURCE_MOCK: "Demo",
}


def _trip_as_logbook_row(trip: dict) -> dict:
    """Render a normalised trip in the shape the logbook PDF builder expects."""
    start = trip.get("start_time")
    end = trip.get("end_time")
    return {
        "date": trip.get("date") or "",
        "start_time": start.astimezone(trips_service.REPORT_TZ).strftime("%H:%M") if start else "",
        "end_time": end.astimezone(trips_service.REPORT_TZ).strftime("%H:%M") if end else "",
        "vehicle_info": trip.get("vehicle_info") or trip.get("vehicle_id") or "",
        "instructor_name": trip.get("instructor_name") or "-",
        "start_location": trip.get("start_address") or "",
        "end_location": trip.get("end_address") or "",
        "start_odometer": "",
        "end_odometer": "",
        "distance": round(trip.get("distance_km") or 0),
        "purpose": trip.get("purpose") or "",
        "source_label": _SOURCE_LABELS.get(trip.get("source"), trip.get("source") or "?"),
    }


@api_router.get("/logbook/export-pdf")
async def export_logbook_pdf(
    vehicle_id: Optional[str] = None,
    instructor_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    source: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Export the logbook as a PDF.

    The export is built from the unified trip layer, so a drive imported from
    Ruhavik appears in the printed logbook exactly like one recorded by a
    tracker or entered by hand — the `Zdroj` column says which is which.
    """
    trip_list = await _load_report_trips(
        vehicle_id=vehicle_id,
        instructor_id=instructor_id,
        date_from=date_from,
        date_to=date_to,
        source=source,
    )
    entries = [_trip_as_logbook_row(t) for t in trip_list]

    # Manual entries keep their odometer readings, which the normalised view
    # does not carry; fill them back in for the rows that have them.
    manual_ids = [t["trip_id"] for t in trip_list if t["source"] == trips_service.SOURCE_MANUAL]
    if manual_ids:
        raw = await db.logbook.find(
            {"entry_id": {"$in": manual_ids}},
            {"_id": 0, "entry_id": 1, "start_odometer": 1, "end_odometer": 1},
        ).to_list(len(manual_ids) + 10)
        odometers = {r["entry_id"]: r for r in raw}
        for trip, row in zip(trip_list, entries):
            reading = odometers.get(trip["trip_id"])
            if reading:
                row["start_odometer"] = reading.get("start_odometer", "")
                row["end_odometer"] = reading.get("end_odometer", "")

    logger.info(
        "PDF knihy jízd: %d jízd (%s)",
        len(entries),
        ", ".join(f"{k}={v['trips']}" for k, v in trips_service.summarize(trip_list)["by_source"].items()) or "žádné",
    )

    pdf_buf = _build_logbook_pdf(entries, date_from, date_to)
    filename = f"kniha-jizd-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.pdf"

    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ======================== LIVE GPS TRACKING ========================

@api_router.get("/gps/live-positions")
async def get_live_positions(user: User = Depends(get_current_user)):
    """Get latest simulated position for all vehicles."""
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(1000)
    positions = []

    # One indexed lookup per vehicle; the projection keeps route history out of
    # the response entirely.
    for v in vehicles:
        pos = await db.vehicle_positions.find_one(
            {"vehicle_id": v["vehicle_id"]},
            {"_id": 0, "lat": 1, "lng": 1, "speed": 1, "heading": 1, "ignition": 1, "timestamp": 1},
            sort=[("timestamp", -1)],
        )
        if pos:
            parse_datetime_field(pos, "timestamp")
            positions.append({
                "vehicle_id": v["vehicle_id"],
                "vehicle_info": f"{v['brand']} {v['model']} ({v['registration_plate']})",
                "lat": pos["lat"],
                "lng": pos["lng"],
                "speed": pos.get("speed", 0),
                "heading": pos.get("heading", 0),
                "ignition": pos.get("ignition", False),
                "timestamp": pos["timestamp"].isoformat() if isinstance(pos["timestamp"], datetime) else pos["timestamp"],
            })
        else:
            positions.append({
                "vehicle_id": v["vehicle_id"],
                "vehicle_info": f"{v['brand']} {v['model']} ({v['registration_plate']})",
                "lat": None,
                "lng": None,
                "speed": 0,
                "heading": 0,
                "ignition": False,
                "timestamp": None,
            })

    return positions


@api_router.post("/gps/simulate-live")
async def simulate_live_positions(user: User = Depends(get_admin_user)):
    """Generate simulated live position updates (development aid, disabled in production)."""
    _require_mock_data_enabled()
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(100)
    now = datetime.now(timezone.utc)
    updated = 0

    for v in vehicles:
        prev = await db.vehicle_positions.find_one(
            {"vehicle_id": v["vehicle_id"]}, {"_id": 0}, sort=[("timestamp", -1)]
        )

        if prev:
            lat = prev["lat"] + (secrets.randbelow(201) - 100) / 100000
            lng = prev["lng"] + (secrets.randbelow(201) - 100) / 100000
        else:
            lat = 50.0755 + (secrets.randbelow(401) - 200) / 10000
            lng = 14.4378 + (secrets.randbelow(401) - 200) / 10000

        ignition = secrets.randbelow(10) < 7
        speed = secrets.randbelow(61) + 20 if ignition else 0
        heading = secrets.randbelow(360)

        await db.vehicle_positions.insert_one({
            "vehicle_id": v["vehicle_id"],
            "lat": lat,
            "lng": lng,
            "speed": speed,
            "heading": heading,
            "ignition": ignition,
            "source": trips_service.SOURCE_MOCK,
            "timestamp": now.isoformat()
        })
        updated += 1

    return {"message": f"Aktualizovány pozice {updated} vozidel", "count": updated}


@api_router.get("/gps/vehicle-history/{vehicle_id}")
async def get_vehicle_position_history(
    vehicle_id: str,
    limit: int = 100,
    user: User = Depends(get_current_user)
):
    """Get position history for a single vehicle."""
    positions = await db.vehicle_positions.find(
        {"vehicle_id": vehicle_id}, {"_id": 0}
    ).sort("timestamp", -1).to_list(limit)

    for p in positions:
        parse_datetime_field(p, "timestamp")

    return positions


# ======================== TELTONIKA TCP SERVER ========================

teltonika_server = None

# AVL IO id -> canonical parameter, with the deployment's overrides applied.
PARAM_IO_MAP = build_param_io_map({
    PARAM_VEHICLE_MILEAGE: settings.can_vehicle_mileage_io_ids,
    PARAM_TRACKER_MILEAGE: settings.can_tracker_mileage_io_ids,
    PARAM_FUEL_LEVEL_PERCENT: settings.can_fuel_percent_io_ids,
    PARAM_FUEL_LEVEL_LITERS: settings.can_fuel_liters_io_ids,
})


async def on_teltonika_records(imei: str, records: list):
    """Persist AVL records received from a tracker.

    Runs on the TCP server's event loop, so it must stay cheap: positions are
    written with one bulk insert instead of one round trip per record.
    Duplicate positions (a tracker resends everything it did not get an ACK
    for) are rejected by the unique `imei + timestamp` index rather than
    silently doubling the vehicle's mileage.
    """
    device = await db.gps_devices.find_one({"imei": imei}, {"_id": 0})
    if not device:
        logger.warning(
            "Neznámé IMEI %s — %d záznamů zahozeno. Zaregistrujte zařízení v Nastavení trackeru.",
            imei, len(records),
        )
        return

    vehicle_id = device["vehicle_id"]
    now = datetime.now(timezone.utc)

    position_docs = []
    latest_obd = None
    skipped_no_fix = 0

    for rec in records:
        gps = rec.get("gps") or {}
        lat, lng = gps.get("lat"), gps.get("lng")

        # A tracker without a fix reports 0/0; storing that would drag every
        # route to the Gulf of Guinea. Coordinates are the test — a satellite
        # count of zero is *not*: Teltonika emits records on events (ignition,
        # periodic wake) carrying the last known position while the GNSS module
        # is asleep or indoors. Discarding those threw away real positions
        # together with the odometer and ignition data attached to them.
        satellites = gps.get("satellites", 0) or 0
        if lat is None or lng is None or (lat == 0.0 and lng == 0.0):
            skipped_no_fix += 1
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            skipped_no_fix += 1
            continue

        obd = rec.get("obd") or {}
        raw_io = (rec.get("io") or {}).get("io") or {}
        # Canonical values (real odometer in km, fuel level in % / litres),
        # independent of which AVL id this particular model uses for them.
        can_params = extract_vehicle_parameters(raw_io, PARAM_IO_MAP)
        speed = gps.get("speed", 0)
        doc = {
            "vehicle_id": vehicle_id,
            "lat": lat,
            "lng": lng,
            "speed": speed,
            "heading": gps.get("angle", 0),
            "altitude": gps.get("altitude", 0),
            "satellites": satellites,
            # False = position carried over from the last fix, not freshly
            # measured. Kept, but distinguishable.
            "gps_fix": satellites > 0,
            "ignition": bool(obd.get("ignition", {}).get("value", speed > 0)),
            "source": trips_service.SOURCE_TELTONIKA,
            "imei": imei,
            "timestamp": rec["timestamp"].isoformat(),
        }
        if obd:
            doc["obd"] = {k: v["value"] for k, v in obd.items()}
            latest_obd = (rec["timestamp"], obd, raw_io, can_params)
        if can_params:
            doc["can"] = can_params
        position_docs.append(doc)

    inserted = 0
    duplicates = 0
    if position_docs:
        try:
            result = await db.vehicle_positions.insert_many(position_docs, ordered=False)
            inserted = len(result.inserted_ids)
        except BulkWriteError as exc:
            # Duplicate-key errors are expected on a tracker replay; anything
            # else is a real storage problem and must surface.
            write_errors = exc.details.get("writeErrors", []) if exc.details else []
            duplicates = sum(1 for err in write_errors if err.get("code") == 11000)
            other = [err for err in write_errors if err.get("code") != 11000]
            inserted = len(position_docs) - len(write_errors)
            if other:
                logger.error("Ukládání pozic pro IMEI %s selhalo: %s", imei, other[:3])
                raise
        except PyMongoError:
            logger.exception("Ukládání pozic pro IMEI %s selhalo", imei)
            raise

    if latest_obd:
        timestamp, obd, raw_io, can_params = latest_obd
        await db.vehicle_obd.update_one(
            {"vehicle_id": vehicle_id},
            {"$set": {
                "vehicle_id": vehicle_id,
                "imei": imei,
                "data": obd,
                "can": can_params,
                # One snapshot of the raw IO elements per vehicle (an upsert,
                # so it cannot grow): without it there is no way to tell which
                # AVL id a particular tracker actually uses for the odometer.
                "raw_io": {str(k): v for k, v in raw_io.items()},
                "timestamp": timestamp.isoformat(),
                "updated_at": now.isoformat(),
            }},
            upsert=True,
        )

    await db.gps_devices.update_one(
        {"imei": imei},
        {"$set": {"last_seen": now.isoformat(), "status": "online"}}
    )

    mileage = (latest_obd[3] if latest_obd else {}).get(PARAM_VEHICLE_MILEAGE)
    logger.info(
        "IMEI %s → vozidlo %s: %d pozic uloženo, %d duplicit, %d bez souřadnic%s",
        imei, vehicle_id, inserted, duplicates, skipped_no_fix,
        f", tachometr {mileage:.0f} km" if mileage else "",
    )


async def start_teltonika_server():
    """Start the Teltonika TCP receiver.

    A failure to bind is logged and re-raised by the caller's error handling
    rather than being swallowed — a silently missing GPS receiver looks exactly
    like "trackers stopped sending data".
    """
    global teltonika_server
    if not settings.teltonika_enabled:
        logger.warning("Teltonika TCP přijímač je vypnutý (TELTONIKA_ENABLED=false)")
        return
    teltonika_server = TeltonikaTCPServer(
        host=settings.teltonika_host,
        port=settings.teltonika_port,
        on_records=on_teltonika_records,
        idle_timeout=settings.teltonika_idle_timeout,
    )
    await teltonika_server.start()


# ── Device management endpoints ──

@api_router.get("/gps/devices")
async def get_gps_devices(user: User = Depends(get_current_user)):
    """List all registered GPS tracker devices."""
    devices = await db.gps_devices.find({}, {"_id": 0}).to_list(500)
    for d in devices:
        parse_datetime_field(d, "created_at")
        parse_datetime_field(d, "last_seen")
    await enrich_many(devices)
    return devices


@api_router.post("/gps/devices")
async def register_gps_device(data: GPSDeviceCreate, user: User = Depends(get_admin_user)):
    """Register a new GPS tracker device (IMEI → vehicle mapping)."""
    existing = await db.gps_devices.find_one({"imei": data.imei}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Zařízení s tímto IMEI je již registrováno")

    vehicle = await db.vehicles.find_one({"vehicle_id": data.vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    now = datetime.now(timezone.utc)
    device = {
        "device_id": f"dev_{uuid.uuid4().hex[:12]}",
        "imei": data.imei,
        "vehicle_id": data.vehicle_id,
        "name": data.name or f"FMB003 ({data.imei[-4:]})",
        "status": "offline",
        "last_seen": None,
        "created_at": now.isoformat(),
    }
    await db.gps_devices.insert_one(device)

    device.pop("_id", None)
    parse_datetime_field(device, "created_at")
    await enrich_vehicle_info(device)
    return GPSDevice(**device)


@api_router.delete("/gps/devices/{device_id}")
async def delete_gps_device(device_id: str, user: User = Depends(get_admin_user)):
    """Unregister a GPS tracker device."""
    result = await db.gps_devices.delete_one({"device_id": device_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Zařízení nenalezeno")
    return {"message": "Zařízení odstraněno"}


@api_router.get("/gps/devices/{imei}/raw-io")
async def get_device_raw_io(imei: str, user: User = Depends(get_admin_user)):
    """Every AVL IO element the tracker last sent, and how it was interpreted.

    Which numbered element carries the odometer differs between models and
    depends on whether a CAN adapter is fitted, so this shows the raw list
    next to the mapping actually in use. If the real odometer is arriving
    under an id the application does not know, it shows up here as
    unrecognised and can be mapped with CAN_VEHICLE_MILEAGE_IO_IDS.
    """
    device = await db.gps_devices.find_one({"imei": imei}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Zařízení s tímto IMEI není registrováno")

    snapshot = await db.vehicle_obd.find_one({"vehicle_id": device["vehicle_id"]}, {"_id": 0})
    raw_io = (snapshot or {}).get("raw_io") or {}

    mapped, unmapped = [], []
    for io_id, value in sorted(raw_io.items(), key=lambda kv: int(kv[0])):
        entry = PARAM_IO_MAP.get(int(io_id))
        obd_entry = OBD_IO_MAP.get(int(io_id))
        row = {
            "io_id": int(io_id),
            "raw_value": value,
            "parameter": entry[0] if entry else None,
            "raw_unit": entry[1] if entry else (obd_entry[1] if obd_entry else None),
            "obd_name": obd_entry[0] if obd_entry else None,
        }
        (mapped if entry else unmapped).append(row)

    return {
        "imei": imei,
        "vehicle_id": device["vehicle_id"],
        "last_seen": (snapshot or {}).get("timestamp"),
        "parameters": (snapshot or {}).get("can") or {},
        # Elements the app turns into a canonical parameter (odometer, fuel).
        "mapped": mapped,
        # Everything else the device sends. `obd_name` is set when the value is
        # still understood as a diagnostic reading, just not as odometer/fuel.
        "unmapped": unmapped,
        "configured_mapping": {
            str(io_id): {"parameter": param, "unit": unit}
            for io_id, (param, unit) in sorted(PARAM_IO_MAP.items())
        },
        "hint": (
            "Pokud tachometr chybí, najděte jeho AVL ID v seznamu 'unmapped' "
            "a přidejte ho do CAN_VEHICLE_MILEAGE_IO_IDS (formát 'id' nebo 'id:jednotka', "
            "např. 389 nebo 1176:km)."
        ),
    }


@api_router.get("/gps/tcp-status")
async def get_tcp_status(user: User = Depends(get_current_user)):
    """Get Teltonika TCP server status."""
    if teltonika_server:
        return teltonika_server.stats
    return {
        "running": False,
        "enabled": settings.teltonika_enabled,
        "host": settings.teltonika_host,
        "port": settings.teltonika_port,
        "active_connections": 0,
        "total_records_received": 0,
    }


@api_router.post("/gps/test-teltonika")
async def test_teltonika_device(
    imei: str,
    lat: float = Query(50.0755, ge=-90, le=90),
    lng: float = Query(14.4378, ge=-180, le=180),
    speed: int = Query(45, ge=0, le=400),
    user: User = Depends(get_admin_user)
):
    """Send one synthetic AVL record to the local TCP receiver.

    Diagnostic aid for verifying that a registered IMEI reaches the database
    without waiting for real hardware. It connects to the receiver on loopback
    only, and writes a position exactly as a real tracker would — so it stays
    behind the mock-data flag.
    """
    _require_mock_data_enabled()
    if not (teltonika_server and teltonika_server.is_running):
        raise HTTPException(status_code=503, detail="Teltonika TCP přijímač neběží")

    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", settings.teltonika_port), timeout=5
        )

        writer.write(build_imei_packet(imei))
        await writer.drain()
        resp = await asyncio.wait_for(reader.readexactly(1), timeout=5)
        if resp != b"\x01":
            return {"success": False, "error": "IMEI odmítnuto přijímačem"}

        writer.write(build_avl_packet([{"lat": lat, "lng": lng, "speed": speed, "altitude": 200}]))
        await writer.drain()
        ack = await asyncio.wait_for(reader.readexactly(4), timeout=10)
        ack_count = struct.unpack(">I", ack)[0]

        return {
            "success": True, "records_acked": ack_count,
            "imei": imei, "lat": lat, "lng": lng, "speed": speed,
        }
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as exc:
        logger.warning("Testovací Teltonika paket selhal: %s", exc)
        return {"success": False, "error": str(exc)}
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass


# ======================== OBD-II DIAGNOSTICS ========================

@api_router.get("/obd/vehicles")
async def get_all_obd_data(user: User = Depends(get_current_user)):
    """Get latest OBD-II diagnostic data for all vehicles."""
    obd_docs = await db.vehicle_obd.find({}, {"_id": 0}).to_list(500)
    for doc in obd_docs:
        parse_datetime_field(doc, "timestamp")
        parse_datetime_field(doc, "updated_at")
    await enrich_many(obd_docs)
    return obd_docs


@api_router.get("/obd/vehicle/{vehicle_id}")
async def get_vehicle_obd_data(vehicle_id: str, user: User = Depends(get_current_user)):
    """Get latest OBD-II data for a specific vehicle."""
    doc = await db.vehicle_obd.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not doc:
        return {"vehicle_id": vehicle_id, "data": {}, "message": "Žádná OBD data"}
    await enrich_vehicle_info(doc)
    return doc


@api_router.get("/obd/vehicle/{vehicle_id}/history")
async def get_vehicle_obd_history(
    vehicle_id: str,
    limit: int = 200,
    user: User = Depends(get_current_user)
):
    """Get OBD-II data history from position records for a vehicle."""
    positions = await db.vehicle_positions.find(
        {"vehicle_id": vehicle_id, "obd": {"$exists": True}},
        {"_id": 0, "timestamp": 1, "obd": 1, "speed": 1}
    ).sort("timestamp", -1).to_list(limit)

    for p in positions:
        parse_datetime_field(p, "timestamp")
    return positions


# ======================== AUTO-TRIP DETECTION ========================

def _build_trip_doc(vehicle_id: str, trip_start: dict, trip_points: list) -> tuple:
    """Build a trip document from a detected trip. Returns (document, distance_m)."""
    trip_end = trip_points[-1]
    end_ts = trip_end.get("timestamp")
    if isinstance(end_ts, str):
        end_ts = datetime.fromisoformat(end_ts)

    distance = sum(
        _haversine(trip_points[i]["lat"], trip_points[i]["lng"],
                   trip_points[i + 1]["lat"], trip_points[i + 1]["lng"])
        for i in range(len(trip_points) - 1)
    )
    speeds = [p.get("speed", 0) for p in trip_points if p.get("speed", 0) > 0]
    now = datetime.now(timezone.utc)
    start_time = trip_start["time"]

    return {
        "trip_id": f"gps_{uuid.uuid4().hex[:12]}",
        "vehicle_id": vehicle_id,
        "source": trips_service.SOURCE_TELTONIKA,
        "duplicate_of": None,
        "start_time": start_time.isoformat() if isinstance(start_time, datetime) else start_time,
        "end_time": end_ts.isoformat() if isinstance(end_ts, datetime) else end_ts,
        "start_location": {"lat": trip_start["lat"], "lng": trip_start["lng"], "address": "GPS"},
        "end_location": {"lat": trip_end["lat"], "lng": trip_end["lng"], "address": "GPS"},
        "route_points": [{"lat": p["lat"], "lng": p["lng"], "timestamp": p.get("timestamp", "")} for p in trip_points],
        "distance": int(distance),
        "max_speed": max(speeds) if speeds else 0,
        "avg_speed": int(sum(speeds) / len(speeds)) if speeds else 0,
        "synced_to_logbook": False,
        "auto_detected": True,
        "created_at": now.isoformat(),
    }, distance


#: A gap this long between two positions ends a drive even without an
#: ignition-off record — trackers miss the last record often enough that
#: otherwise two days of driving merge into one endless trip.
TRIP_MAX_GAP_MINUTES = 20

#: How far back a scheduled run re-examines positions, so a drive that was
#: still in progress at the previous run is picked up once it finishes.
TRIP_DETECTION_OVERLAP_HOURS = 6


async def _detect_trips_for_vehicle(vehicle_id: str, since: Optional[datetime] = None) -> dict:
    """Turn a vehicle's stored positions into trips.

    Splits on ignition going off and on a long gap between positions. Every
    candidate is checked against what is already stored, so running this
    repeatedly — which the scheduler does — cannot multiply a drive.
    """
    query: Dict[str, Any] = {"vehicle_id": vehicle_id}
    if since is not None:
        range_filter = trips_service.timestamp_range_query("timestamp", since, None)
        if range_filter:
            query.update(range_filter)

    positions = await db.vehicle_positions.find(
        query, {"_id": 0, "lat": 1, "lng": 1, "speed": 1, "ignition": 1, "timestamp": 1}
    ).sort("timestamp", 1).to_list(50000)

    if len(positions) < 2:
        return {"trips": 0, "skipped_existing": 0, "positions": len(positions)}

    trips_created = 0
    trips_skipped = 0
    trip_start = None
    trip_points: List[dict] = []
    previous_at = None

    async def close_trip() -> None:
        nonlocal trips_created, trips_skipped, trip_start, trip_points
        if trip_start is not None and len(trip_points) >= 2:
            trip_doc, distance = _build_trip_doc(vehicle_id, trip_start, trip_points)
            if distance >= 100:
                existing = await trips_service.find_duplicate_trip(db, trip_doc)
                if existing:
                    trips_skipped += 1
                else:
                    await db.gps_trips.insert_one(trip_doc)
                    trips_created += 1
        trip_start = None
        trip_points = []

    for pos in positions:
        at = trips_service.to_utc(pos.get("timestamp"))
        if at is None:
            continue
        ignition = pos.get("ignition", (pos.get("speed", 0) or 0) > 0)

        # A long silence ends the drive even if the ignition-off record never
        # arrived (tracker out of signal, battery pulled, records dropped).
        if (previous_at is not None and trip_start is not None
                and (at - previous_at).total_seconds() > TRIP_MAX_GAP_MINUTES * 60):
            await close_trip()
        previous_at = at

        if ignition and trip_start is None:
            trip_start = {"time": at, "lat": pos["lat"], "lng": pos["lng"]}
            trip_points = [pos]
        elif ignition:
            trip_points.append(pos)
        elif trip_start is not None:
            await close_trip()

    # A drive left open at the end of the data: close it once the last position
    # is older than the gap threshold, because then the vehicle plainly is not
    # still driving — the tracker simply never sent the ignition-off record.
    # A genuinely in-progress drive (recent last position) stays open and is
    # picked up by the next run thanks to the overlap.
    if trip_start is not None and previous_at is not None:
        idle = datetime.now(timezone.utc) - previous_at
        if idle > timedelta(minutes=TRIP_MAX_GAP_MINUTES):
            await close_trip()

    return {"trips": trips_created, "skipped_existing": trips_skipped,
            "positions": len(positions)}


@api_router.post("/gps/detect-trips/{vehicle_id}")
async def detect_trips_from_positions(vehicle_id: str, user: User = Depends(get_current_user)):
    """Detect trips from a vehicle's whole position history (manual run)."""
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    result = await _detect_trips_for_vehicle(vehicle_id)
    if result["positions"] < 2:
        return {"message": "Nedostatek dat pro detekci jízd", "trips": 0}

    logger.info(
        "Detekce jízd pro vozidlo %s: %d nových, %d již existovalo",
        vehicle_id, result["trips"], result["skipped_existing"],
    )
    return {
        "message": f"Detekováno {result['trips']} jízd ({result['skipped_existing']} již existovalo)",
        "trips": result["trips"],
        "skipped_existing": result["skipped_existing"],
    }


async def trip_detection_loop():
    """Turn incoming tracker positions into trips, without anyone clicking.

    Positions used to become trips only when somebody pressed a button, so a
    fleet could stream GPS data for weeks and still report zero drives — the
    logbook and every trip report stayed empty. This closes that gap.
    """
    await asyncio.sleep(45)  # let startup settle
    interval = max(60, settings.trip_detection_interval_sec)
    while True:
        try:
            if settings.trip_detection_enabled:
                since = datetime.now(timezone.utc) - timedelta(hours=TRIP_DETECTION_OVERLAP_HOURS)
                vehicle_ids = await db.vehicle_positions.distinct(
                    "vehicle_id", trips_service.timestamp_range_query("timestamp", since, None) or {}
                )
                total_new = 0
                for vehicle_id in vehicle_ids:
                    result = await _detect_trips_for_vehicle(vehicle_id, since=since)
                    total_new += result["trips"]
                if total_new:
                    logger.info(
                        "Automatická detekce jízd: %d nových jízd u %d vozidel",
                        total_new, len(vehicle_ids),
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Automatická detekce jízd selhala")
        await asyncio.sleep(interval)


def _haversine(lat1, lng1, lat2, lng2):
    """Calculate distance in meters between two GPS points."""
    import math
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ======================== FILE UPLOAD ========================

# ======================== MAINTENANCE ROUTES ========================

@api_router.get("/maintenance")
async def get_maintenance_items(
    vehicle_id: Optional[str] = None,
    status: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Get maintenance items with optional filters"""
    query = {}
    if vehicle_id:
        query["vehicle_id"] = vehicle_id
    items = await db.maintenance.find(query, {"_id": 0}).sort("next_due_date", 1).to_list(1000)
    await enrich_many(items)
    documents = await _load_documents([i["maintenance_id"] for i in items])
    results = []
    for item in items:
        parse_datetime_field(item, "created_at")
        parse_datetime_field(item, "updated_at")
        item["status"] = compute_maintenance_status(item)
        item["documents"] = documents.get(item["maintenance_id"], [])
        if status and item["status"] != status:
            continue
        results.append(MaintenanceItem(**item))
    return results


@api_router.get("/maintenance/summary")
async def get_maintenance_summary(user: User = Depends(get_current_user)):
    """Get maintenance summary with upcoming/overdue counts"""
    items = await db.maintenance.find({}, {"_id": 0}).to_list(1000)
    total = len(items)
    overdue = 0
    upcoming = 0
    ok_count = 0
    for item in items:
        s = compute_maintenance_status(item)
        if s == "po termínu":
            overdue += 1
        elif s == "blíží se":
            upcoming += 1
        else:
            ok_count += 1
    return {"total": total, "overdue": overdue, "upcoming": upcoming, "ok": ok_count}


@api_router.get("/maintenance/{maintenance_id}", response_model=MaintenanceItem)
async def get_maintenance_item(maintenance_id: str, user: User = Depends(get_current_user)):
    """One maintenance item including its photographed documents."""
    item = await db.maintenance.find_one({"maintenance_id": maintenance_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Záznam údržby nenalezen")
    parse_datetime_field(item, "created_at")
    parse_datetime_field(item, "updated_at")
    item["status"] = compute_maintenance_status(item)
    item["documents"] = (await _load_documents([maintenance_id])).get(maintenance_id, [])
    await enrich_vehicle_info(item)
    return MaintenanceItem(**item)


@api_router.post("/maintenance", response_model=MaintenanceItem)
async def create_maintenance_item(data: MaintenanceItemCreate, user: User = Depends(get_admin_user)):
    """Create a new maintenance item"""
    maintenance_id = f"mnt_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    item = {
        "maintenance_id": maintenance_id,
        **data.model_dump(),
        "status": "ok",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    }
    item["status"] = compute_maintenance_status(item)
    await db.maintenance.insert_one(item)
    item["created_at"] = now
    item["updated_at"] = now
    await enrich_vehicle_info(item)
    return MaintenanceItem(**item)


@api_router.put("/maintenance/{maintenance_id}", response_model=MaintenanceItem)
async def update_maintenance_item(maintenance_id: str, data: MaintenanceItemCreate, user: User = Depends(get_admin_user)):
    """Update a maintenance item"""
    existing = await db.maintenance.find_one({"maintenance_id": maintenance_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Záznam údržby nenalezen")
    now = datetime.now(timezone.utc)
    update_data = {**data.model_dump(), "updated_at": now.isoformat()}
    await db.maintenance.update_one({"maintenance_id": maintenance_id}, {"$set": update_data})
    updated = await db.maintenance.find_one({"maintenance_id": maintenance_id}, {"_id": 0})
    parse_datetime_field(updated, "created_at")
    updated["updated_at"] = now
    updated["status"] = compute_maintenance_status(updated)
    await enrich_vehicle_info(updated)
    return MaintenanceItem(**updated)


@api_router.delete("/maintenance/{maintenance_id}")
async def delete_maintenance_item(maintenance_id: str, user: User = Depends(get_admin_user)):
    """Delete a maintenance item"""
    result = await db.maintenance.delete_one({"maintenance_id": maintenance_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Záznam údržby nenalezen")
    # Otherwise the photographed documents stay behind as orphans nobody can
    # reach or delete.
    removed = await db.maintenance_documents.delete_many({"maintenance_id": maintenance_id})
    return {"message": "Záznam údržby smazán", "documents_deleted": removed.deleted_count}


# ── Photographed service / maintenance documents ──
# Invoices, STK protocols and service-book pages are photographed on a phone
# and attached to the maintenance record they belong to. The binary lives in
# its own collection so a maintenance list stays small.

ALLOWED_DOCUMENT_TYPES = ALLOWED_UPLOAD_TYPES | {"application/pdf"}


async def _load_documents(maintenance_ids: List[str]) -> Dict[str, List[dict]]:
    """Document metadata for the given maintenance items, in one query."""
    if not maintenance_ids:
        return {}
    docs = await db.maintenance_documents.find(
        {"maintenance_id": {"$in": maintenance_ids}},
        {"_id": 0, "data": 0},          # never load the image bytes here
    ).sort("uploaded_at", 1).to_list(2000)
    grouped: Dict[str, List[dict]] = {}
    for doc in docs:
        parse_datetime_field(doc, "uploaded_at")
        doc["url"] = f"/api/maintenance/documents/{doc['document_id']}/file"
        grouped.setdefault(doc["maintenance_id"], []).append(doc)
    return grouped


@api_router.post("/maintenance/{maintenance_id}/documents", response_model=MaintenanceDocument)
async def upload_maintenance_document(
    maintenance_id: str,
    file: UploadFile = File(...),
    doc_type: str = Form("foto"),
    label: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
):
    """Attach a photographed document (invoice, STK protocol, receipt, …)."""
    item = await db.maintenance.find_one({"maintenance_id": maintenance_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Záznam údržby nenalezen")

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Nepodporovaný typ souboru: {content_type or 'neznámý'}. "
                   f"Povolené: {', '.join(sorted(ALLOWED_DOCUMENT_TYPES))}.",
        )
    content = await _read_upload(file, settings.max_upload_bytes)
    if not content:
        raise HTTPException(status_code=400, detail="Nahraný soubor je prázdný.")

    if doc_type not in MAINTENANCE_DOC_TYPES:
        doc_type = "jiné"

    now = datetime.now(timezone.utc)
    document_id = f"mdoc_{uuid.uuid4().hex[:12]}"
    # Stored as BSON binary rather than a base64 string: a third smaller, and
    # it can be streamed back without a decode step.
    await db.maintenance_documents.insert_one({
        "document_id": document_id,
        "maintenance_id": maintenance_id,
        "vehicle_id": item["vehicle_id"],
        "doc_type": doc_type,
        "label": (label or "").strip() or None,
        "filename": os.path.basename(file.filename or "dokument"),
        "content_type": content_type,
        "size_bytes": len(content),
        "data": content,
        "uploaded_at": now.isoformat(),
        "uploaded_by": user.email or user.name,
    })
    logger.info(
        "Doklad k údržbě %s nahrán (%s, %.1f kB) uživatelem %s",
        maintenance_id, doc_type, len(content) / 1024, user.user_id,
    )

    return MaintenanceDocument(
        document_id=document_id, doc_type=doc_type, label=(label or "").strip() or None,
        filename=os.path.basename(file.filename or "dokument"), content_type=content_type,
        size_bytes=len(content), url=f"/api/maintenance/documents/{document_id}/file",
        uploaded_at=now, uploaded_by=user.email or user.name,
    )


@api_router.get("/maintenance/documents/{document_id}/file")
async def get_maintenance_document_file(document_id: str, user: User = Depends(get_current_user)):
    """Stream a stored document image/PDF."""
    doc = await db.maintenance_documents.find_one({"document_id": document_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Doklad nenalezen")
    data = doc.get("data") or b""
    if isinstance(data, str):  # tolerate a legacy base64 payload
        data = base64.b64decode(data)
    filename = doc.get("filename") or "dokument"
    return StreamingResponse(
        io.BytesIO(bytes(data)),
        media_type=doc.get("content_type", "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            # Documents never change once uploaded, and the id is unguessable.
            "Cache-Control": "private, max-age=86400",
        },
    )


@api_router.delete("/maintenance/documents/{document_id}")
async def delete_maintenance_document(document_id: str, user: User = Depends(get_admin_user)):
    """Remove a stored document."""
    result = await db.maintenance_documents.delete_one({"document_id": document_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Doklad nenalezen")
    logger.info("Doklad k údržbě %s smazán uživatelem %s", document_id, user.user_id)
    return {"message": "Doklad smazán"}


# ======================== RUHAVIK IMPORT ROUTES ========================
# Parsing and idempotent persistence live in `ruhavik.py`; this layer only
# handles HTTP concerns (upload limits, vehicle lookup, reporting the result).


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload, refusing anything over the configured limit.

    Read in chunks so an oversized file is rejected without first buffering it
    all in memory.
    """
    chunks = []
    total = 0
    while True:
        chunk = await file.read(1024 * 256)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Soubor je příliš velký (limit {max_bytes // (1024 * 1024)} MB).",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@api_router.post("/gps/import-ruhavik")
async def import_ruhavik_data(
    vehicle_id: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user)
):
    """Import drives from a Ruhavik CSV or GPX export.

    The import is idempotent: every drive carries a stable identifier, so
    uploading the same export twice reports the drives as already imported
    instead of duplicating them. Individual unreadable records are counted and
    reported; they never abort the rest of the file. Imported drives are stored
    with ``source = "ruhavik"`` and are therefore part of every trip report.
    """
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    raw = await _read_upload(file, settings.max_import_bytes)
    if not raw:
        raise HTTPException(status_code=400, detail="Nahraný soubor je prázdný.")
    content = raw.decode("utf-8-sig", errors="replace")

    try:
        candidates, parse_errors, detected_format = ruhavik_import.parse_ruhavik_file(
            file.filename or "", content, vehicle_id
        )
    except ruhavik_import.ImportError_ as exc:
        logger.info("Ruhavik import odmítnut (%s): %s", file.filename, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Ruhavik import selhal na neočekávané chybě")
        raise HTTPException(status_code=400, detail=f"Soubor se nepodařilo zpracovat: {exc}") from exc

    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="V souboru nebyla nalezena žádná jízda. "
                   + (f"Chyby: {'; '.join(parse_errors[:3])}" if parse_errors else ""),
        )

    result = await ruhavik_import.store_trips(db, candidates)
    total_rejected = result["rejected"] + len(parse_errors)

    logger.info(
        "Ruhavik import (%s, formát %s, vozidlo %s): %d nových jízd, %d duplicit trackeru, "
        "%d již importovaných, %d chybných záznamů",
        file.filename, detected_format, vehicle_id, result["imported"],
        result["duplicates_of_tracker"], result["skipped_already_imported"], total_rejected,
    )

    message_parts = [f"Importováno {result['imported']} jízd"]
    if result["duplicates_of_tracker"]:
        message_parts.append(f"{result['duplicates_of_tracker']} označeno jako duplicita GPS jízdy")
    if result["skipped_already_imported"]:
        message_parts.append(f"{result['skipped_already_imported']} již bylo importováno dříve")
    if total_rejected:
        message_parts.append(f"{total_rejected} záznamů se nepodařilo načíst")

    return {
        "message": ", ".join(message_parts),
        "format": detected_format,
        "vehicle_id": vehicle_id,
        "imported": result["imported"],
        "duplicates_of_tracker": result["duplicates_of_tracker"],
        "skipped_already_imported": result["skipped_already_imported"],
        "rejected": total_rejected,
        "errors": (parse_errors + result["rejected_details"])[:20],
        "trip_ids": result["trip_ids"],
        # Kept for backwards compatibility with the existing frontend.
        "trips_count": result["imported"],
    }


# ======================== UPLOAD & ROOT ========================

async def _image_to_data_url(file: UploadFile) -> dict:
    """Validate an uploaded image and return it as a data URL.

    Uploads are inlined as base64 data URLs (that is how photos are stored in
    this application), so both the media type and the size have to be checked:
    an unbounded upload would otherwise be echoed straight into a MongoDB
    document.
    """
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Nepodporovaný typ souboru: {content_type or 'neznámý'}. "
                   f"Povolené: {', '.join(sorted(ALLOWED_UPLOAD_TYPES))}.",
        )
    content = await _read_upload(file, settings.max_upload_bytes)
    if not content:
        raise HTTPException(status_code=400, detail="Nahraný soubor je prázdný.")
    base64_content = base64.b64encode(content).decode("utf-8")
    # The original filename is never used as a path, and it is not echoed back
    # verbatim either — only its basename, so it cannot carry directory parts.
    safe_name = os.path.basename(file.filename or "upload")
    return {"url": f"data:{content_type};base64,{base64_content}", "filename": safe_name}


@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Upload an image and return it as a base64 data URL."""
    return await _image_to_data_url(file)


@api_router.post("/public/upload")
async def public_upload_file(file: UploadFile = File(...)):
    """Upload an image from a QR flow (public endpoint)."""
    return await _image_to_data_url(file)

# ======================== RESERVATION REPORTS (Report ujetých km) ========================
import re as _re
from collections import defaultdict as _defaultdict

DEFAULT_RESERVATION_SETTINGS = {
    "base_limit_km": 60.0,
    "minutes_per_hour_unit": 45,   # 1 "hodina" ve výcviku = 45 min
    "gps_tz_offset_hours": 2,      # posun místního času vůči UTC v GPS datech
    "private_by_instructor": True,  # smí instruktor označit jízdu jako soukromou
    "ics_auto_sync": True,          # automatická synchronizace ICS kalendářů
    "ics_sync_interval_minutes": 60,  # jak často (min)
    "locations": ["Karlovy Vary, Dolní nádraží", "Ostrov, Učebna"],
    "distances": [
        {"from": "Karlovy Vary, Dolní nádraží", "to": "Ostrov, Učebna", "km": 12.0},
    ],
}


def _norm_loc(name):
    if not name:
        return ""
    s = str(name).replace("[mapa]", "").strip()
    s = _re.sub(r"\s+", " ", s)
    return s.rstrip(" ,")


def _loc_key(name):
    return _norm_loc(name).lower()


async def get_reservation_settings() -> dict:
    doc = await db.app_settings.find_one({"key": "reservations"}, {"_id": 0})
    settings = dict(DEFAULT_RESERVATION_SETTINGS)
    if doc:
        for k in DEFAULT_RESERVATION_SETTINGS:
            if k in doc and doc[k] is not None:
                settings[k] = doc[k]
    return settings


def _distance_between(res_settings, loc_a, loc_b):
    ka, kb = _loc_key(loc_a), _loc_key(loc_b)
    if not ka or not kb or ka == kb:
        return 0.0
    for d in res_settings.get("distances", []):
        df, dt = _loc_key(d.get("from")), _loc_key(d.get("to"))
        if {df, dt} == {ka, kb}:
            try:
                return float(d.get("km") or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _parse_datum(raw):
    """'St 1.7.2026 (08:00)' -> (date_iso, naive datetime)."""
    if not raw:
        return None, None
    s = str(raw)
    m = _re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4}).*?\((\d{1,2}):(\d{2})\)", s)
    if m:
        d, mo, y, hh, mm = (int(m.group(i)) for i in range(1, 6))
        try:
            dt = datetime(y, mo, d, hh, mm)
            return dt.date().isoformat(), dt
        except ValueError:
            return None, None
    m2 = _re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m2:
        d, mo, y = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        try:
            dt = datetime(y, mo, d, 0, 0)
            return dt.date().isoformat(), dt
        except ValueError:
            return None, None
    return None, None


def _parse_num(raw):
    if raw is None:
        return None
    s = str(raw).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if s in ("", "???", "-", "nan", "NaN", "None"):
        return None
    m = _re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def parse_reservation_file(content: bytes):
    """Parse the reservation export (HTML table saved as .xls) into row dicts."""
    from bs4 import BeautifulSoup
    text = content.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    rows = table.find_all("tr")
    if not rows:
        return []
    header_cells = rows[0].find_all(["th", "td"])
    headers = [c.get_text(strip=True).lower() for c in header_cells]

    def find_idx(*keys):
        for i, h in enumerate(headers):
            for k in keys:
                if k in h:
                    return i
        return None

    idx_datum = find_idx("datum")
    idx_hodin = find_idx("hodin")
    idx_ucitel = find_idx("učitel", "ucitel")
    idx_stan = find_idx("stanoviš", "stanovis")
    idx_voz = find_idx("vozidlo")
    idx_skup = find_idx("skupina")
    idx_zak = find_idx("zákazník", "zakaznik")
    idx_pozn = find_idx("poznám", "poznam")
    idx_tacho_start = idx_tacho_end = None
    for i, h in enumerate(headers):
        if "tacho" in h and ("zač" in h or "zac" in h):
            idx_tacho_start = i
        if "tacho" in h and "kon" in h:
            idx_tacho_end = i
    km_idxs = [i for i, h in enumerate(headers) if h == "km" or h.startswith("km")]
    idx_km_res = km_idxs[0] if km_idxs else None
    idx_km_calc = km_idxs[1] if len(km_idxs) > 1 else None

    out = []
    for r in rows[1:]:
        cells = r.find_all(["td", "th"])
        if not cells:
            continue
        vals = [c.get_text(" ", strip=True) for c in cells]

        def gv(i):
            if i is None or i >= len(vals):
                return None
            v = vals[i]
            return v if v not in ("", "nan") else None

        out.append({
            "datum": gv(idx_datum),
            "hodin": gv(idx_hodin),
            "teacher": gv(idx_ucitel),
            "boarding": gv(idx_stan),
            "vehicle_name": gv(idx_voz),
            "activity": gv(idx_skup),
            "customer": gv(idx_zak),
            "reservation_km": gv(idx_km_res),
            "tacho_start": gv(idx_tacho_start),
            "tacho_end": gv(idx_tacho_end),
            "km_calc": gv(idx_km_calc),
            "note": gv(idx_pozn),
        })
    return out


async def _match_or_create_vehicle(vehicle_name, cache):
    if not vehicle_name:
        return None
    name = str(vehicle_name).strip()
    key = name.lower()
    if key in cache:
        return cache[key]
    v = await db.vehicles.find_one(
        {"reservation_alias": {"$regex": f"^{_re.escape(name)}$", "$options": "i"}}, {"_id": 0}
    )
    if not v:
        all_v = await db.vehicles.find({}, {"_id": 0}).to_list(500)
        for cand in all_v:
            combo = f"{cand.get('brand', '')} {cand.get('model', '')}".strip().lower()
            plate = str(cand.get("registration_plate", "")).strip().lower()
            if (combo and (combo == key or combo in key or key in combo)) or plate == key:
                v = cand
                break
    if v:
        vid = v["vehicle_id"]
        if not v.get("reservation_alias"):
            await db.vehicles.update_one({"vehicle_id": vid}, {"$set": {"reservation_alias": name}})
        cache[key] = vid
        return vid
    # auto-create a placeholder vehicle
    vehicle_id = f"veh_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    parts = name.split()
    brand = parts[0] if parts else name
    model = " ".join(parts[1:]) if len(parts) > 1 else ""
    await db.vehicles.insert_one({
        "vehicle_id": vehicle_id,
        "registration_plate": name[:20],
        "brand": brand,
        "model": model,
        "year": 0,
        "vin": None,
        "odometer": 0,
        "fuel_type": "benzín",
        "assigned_instructor_id": None,
        "reservation_alias": name,
        "qr_code_fuel": f"fuel_{vehicle_id}",
        "qr_code_damage": f"damage_{vehicle_id}",
        "qr_code_handover": f"handover_{vehicle_id}",
        "auto_created": True,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    })
    cache[key] = vehicle_id
    return vehicle_id


async def _load_positions(vehicle_id, start_utc=None, end_utc=None):
    """Load a vehicle's GPS positions, optionally bounded to a time window.

    Without a window this pulled a vehicle's entire recorded history for every
    reservation report — hundreds of thousands of points to evaluate a single
    week. The bounded query uses the (vehicle_id, timestamp) index; the exact
    per-drive filtering still happens in `_km_in_window`.
    """
    if not vehicle_id:
        return []
    query = {"vehicle_id": vehicle_id}
    if start_utc or end_utc:
        lo = (start_utc - timedelta(minutes=5)).replace(tzinfo=timezone.utc) if start_utc else None
        hi = (end_utc + timedelta(minutes=5)).replace(tzinfo=timezone.utc) if end_utc else None
        range_filter = trips_service.timestamp_range_query("timestamp", lo, hi)
        if range_filter:
            query.update(range_filter)
    positions = await db.vehicle_positions.find(
        query, {"_id": 0, "lat": 1, "lng": 1, "timestamp": 1}
    ).to_list(200000)
    parsed = []
    for p in positions:
        ts, la, ln = p.get("timestamp"), p.get("lat"), p.get("lng")
        if ts is None or la is None or ln is None:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
            if getattr(dt, "tzinfo", None) is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        except (ValueError, TypeError, AttributeError):
            continue
        parsed.append((dt, la, ln))
    parsed.sort(key=lambda x: x[0])
    return parsed


def _km_in_window(positions, start_utc, end_utc):
    """positions and start/end are all naive UTC."""
    if not positions or not start_utc or not end_utc:
        return {"gps_km": None, "points": [], "available": False}
    pts = [(dt, la, ln) for (dt, la, ln) in positions if start_utc <= dt <= end_utc]
    points = [{"lat": la, "lng": ln} for _, la, ln in pts]
    if len(pts) < 2:
        return {"gps_km": None, "points": points, "available": False}
    meters = 0.0
    for i in range(1, len(pts)):
        meters += _haversine(pts[i - 1][1], pts[i - 1][2], pts[i][1], pts[i][2])
    return {"gps_km": round(meters / 1000.0, 1), "points": points, "available": True}


def _drive_window_utc(drive, tz_off):
    """Return (start_utc_naive, end_utc_naive). Uses start_utc if present (ICS),
    else converts local start_datetime with tz offset (xls)."""
    su = drive.get("start_utc")
    if su:
        start = datetime.fromisoformat(su)
        if start.tzinfo is not None:
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        sd = drive.get("start_datetime")
        if not sd:
            return None, None
        start_local = datetime.fromisoformat(sd)
        if start_local.tzinfo is not None:
            start_local = start_local.replace(tzinfo=None)
        start = start_local - timedelta(hours=tz_off)
    dur = drive.get("duration_min")
    if not dur:
        return start, None
    return start, start + timedelta(minutes=dur)


def _instructor_match(teacher, instr_name):
    if not teacher or not instr_name:
        return False
    t = teacher.lower()
    tokens = [tok for tok in _re.split(r"[^0-9a-zá-žě-ú]+", instr_name.lower()) if len(tok) >= 3]
    return any(tok in t for tok in tokens)


@api_router.post("/reservations/import")
async def import_reservations(file: UploadFile = File(...), user: User = Depends(get_admin_user)):
    """Import a reservation-system export and store parsed drives."""
    content = await _read_upload(file, settings.max_import_bytes)
    if not content:
        raise HTTPException(status_code=400, detail="Nahraný soubor je prázdný.")
    try:
        rows = parse_reservation_file(content)
    except Exception as exc:
        logger.warning("Import rezervací (%s) se nepodařilo načíst: %s", file.filename, exc)
        raise HTTPException(status_code=400, detail=f"Nepodařilo se načíst soubor: {exc}") from exc
    if not rows:
        raise HTTPException(status_code=400, detail="V souboru nebyla nalezena žádná data")

    res_settings = await get_reservation_settings()
    mpu = res_settings.get("minutes_per_hour_unit", 45)
    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    cache = {}
    drives = []
    skipped = 0

    for row in rows:
        date_iso, start_dt = _parse_datum(row.get("datum"))
        if not start_dt:
            skipped += 1
            continue
        hours = _parse_num(row.get("hodin"))
        duration_min = int(round(hours * mpu)) if (hours is not None and 0 < hours <= 12) else None
        vehicle_id = await _match_or_create_vehicle(row.get("vehicle_name"), cache)
        drives.append({
            "drive_id": f"drv_{uuid.uuid4().hex[:12]}",
            "batch_id": batch_id,
            "date": date_iso,
            "start_datetime": start_dt.isoformat(),
            "hours": hours,
            "duration_min": duration_min,
            "teacher": row.get("teacher"),
            "vehicle_name": row.get("vehicle_name"),
            "vehicle_id": vehicle_id,
            "boarding_location": _norm_loc(row.get("boarding")),
            "activity": row.get("activity"),
            "customer": row.get("customer"),
            "reservation_km": _parse_num(row.get("reservation_km")) if _parse_num(row.get("reservation_km")) is not None else _parse_num(row.get("km_calc")),
            "tacho_start": _parse_num(row.get("tacho_start")),
            "tacho_end": _parse_num(row.get("tacho_end")),
            "note": row.get("note"),
            "is_private": False,
            "created_at": now.isoformat(),
        })

    if drives:
        await db.reservation_drives.insert_many(drives)
    await db.reservation_batches.insert_one({
        "batch_id": batch_id,
        "filename": file.filename,
        "count": len(drives),
        "skipped": skipped,
        "created_at": now.isoformat(),
        "created_by": user.email,
    })
    names = sorted({d["vehicle_name"] for d in drives if d.get("vehicle_name")})
    return {"batch_id": batch_id, "imported": len(drives), "skipped": skipped, "vehicles": names}


@api_router.get("/reservations/drives")
async def get_reservation_drives(
    request: Request,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    vehicle_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    only_exceeded: bool = False,
    user: User = Depends(get_current_user),
):
    """Report of drives with GPS km, tolerance and limit evaluation."""
    query = {}
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    if vehicle_id:
        query["vehicle_id"] = vehicle_id
    if batch_id:
        query["batch_id"] = batch_id

    drives = await db.reservation_drives.find(query, {"_id": 0}).to_list(10000)

    if user.role == "instructor":
        instr = await db.instructors.find_one({"instructor_id": user.user_id}, {"_id": 0})
        assigned = set(instr.get("assigned_vehicle_ids", [])) if instr else set()
        name = instr.get("name") if instr else user.name
        drives = [d for d in drives if (d.get("vehicle_id") in assigned) or _instructor_match(d.get("teacher"), name)]

    res_settings = await get_reservation_settings()
    base_limit = float(res_settings.get("base_limit_km", 60))
    tz_off = res_settings.get("gps_tz_offset_hours", 2)

    # tolerance per drive (group by vehicle + date, ordered by time)
    groups = _defaultdict(list)
    for d in drives:
        groups[(d.get("vehicle_id"), d.get("date"))].append(d)
    tol_map = {}
    for _key, items in groups.items():
        items_sorted = sorted(items, key=lambda x: x.get("start_datetime") or "")
        for i, d in enumerate(items_sorted):
            prev_loc = items_sorted[i - 1].get("boarding_location") if i > 0 else None
            next_loc = items_sorted[i + 1].get("boarding_location") if i < len(items_sorted) - 1 else None
            approach = _distance_between(res_settings, prev_loc, d.get("boarding_location")) if prev_loc else 0.0
            departure = _distance_between(res_settings, d.get("boarding_location"), next_loc) if next_loc else 0.0
            tol_map[d["drive_id"]] = round(approach + departure, 1)

    # Precompute each drive's window once, then load only the GPS positions
    # that fall inside the reported period for each vehicle.
    windows = {d["drive_id"]: _drive_window_utc(d, tz_off) for d in drives}
    per_vehicle_bounds = {}
    for d in drives:
        vid = d.get("vehicle_id")
        start_utc, end_utc = windows[d["drive_id"]]
        if not (vid and start_utc):
            continue
        lo, hi = per_vehicle_bounds.get(vid, (start_utc, end_utc or start_utc))
        per_vehicle_bounds[vid] = (min(lo, start_utc), max(hi, end_utc or start_utc))

    pos_cache = {}
    for vid, (lo, hi) in per_vehicle_bounds.items():
        pos_cache[vid] = await _load_positions(vid, lo, hi)

    result = []
    for d in drives:
        start_utc, end_utc = windows[d["drive_id"]]
        gps = _km_in_window(pos_cache.get(d.get("vehicle_id"), []), start_utc, end_utc)
        tolerance = tol_map.get(d["drive_id"], 0.0)
        eff_limit = round(base_limit + tolerance, 1)
        gps_km = gps["gps_km"]
        exceeded = bool(gps["available"] and gps_km is not None and gps_km > eff_limit)
        item = dict(d)
        item["tolerance_km"] = tolerance
        item["base_limit_km"] = base_limit
        item["effective_limit_km"] = eff_limit
        item["gps_km"] = gps_km
        item["gps_available"] = gps["available"]
        item["route_hidden"] = bool(d.get("is_private"))
        item["exceeded"] = exceeded
        result.append(item)

    result.sort(key=lambda x: x.get("start_datetime") or "")
    if only_exceeded:
        result = [r for r in result if r["exceeded"]]

    summary = {
        "total": len(result),
        "exceeded": sum(1 for r in result if r["exceeded"]),
        "missing_gps": sum(1 for r in result if not r["gps_available"]),
        "total_gps_km": round(sum(r["gps_km"] for r in result if r["gps_km"] is not None), 1),
    }
    return {"drives": result, "summary": summary}


@api_router.get("/reservations/drives/{drive_id}/route")
async def get_reservation_drive_route(drive_id: str, user: User = Depends(get_current_user)):
    d = await db.reservation_drives.find_one({"drive_id": drive_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Jízda nenalezena")
    if d.get("is_private"):
        return {"private": True, "points": [], "gps_km": None}
    res_settings = await get_reservation_settings()
    tz_off = res_settings.get("gps_tz_offset_hours", 2)
    start_utc, end_utc = _drive_window_utc(d, tz_off)
    positions = await _load_positions(d.get("vehicle_id"), start_utc, end_utc)
    gps = _km_in_window(positions, start_utc, end_utc)
    return {"private": False, "points": gps["points"], "gps_km": gps["gps_km"]}


@api_router.patch("/reservations/drives/{drive_id}/private")
async def toggle_drive_private(drive_id: str, request: Request, user: User = Depends(get_current_user)):
    body = await request.json()
    is_private = bool(body.get("is_private"))
    res_settings = await get_reservation_settings()
    if user.role == "instructor" and not res_settings.get("private_by_instructor", True):
        raise HTTPException(status_code=403, detail="Instruktor nemá oprávnění měnit soukromí jízdy")
    res = await db.reservation_drives.update_one({"drive_id": drive_id}, {"$set": {"is_private": is_private}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Jízda nenalezena")
    return {"drive_id": drive_id, "is_private": is_private}


@api_router.get("/reservations/batches")
async def list_reservation_batches(user: User = Depends(get_current_user)):
    return await db.reservation_batches.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@api_router.delete("/reservations/batches/{batch_id}")
async def delete_reservation_batch(batch_id: str, user: User = Depends(get_admin_user)):
    await db.reservation_drives.delete_many({"batch_id": batch_id})
    await db.reservation_batches.delete_one({"batch_id": batch_id})
    return {"message": "Import smazán"}


@api_router.get("/reservations/settings")
async def get_reservation_settings_endpoint(user: User = Depends(get_current_user)):
    return await get_reservation_settings()


@api_router.put("/reservations/settings")
async def update_reservation_settings_endpoint(request: Request, user: User = Depends(get_admin_user)):
    body = await request.json()
    allowed = set(DEFAULT_RESERVATION_SETTINGS.keys())
    update = {k: v for k, v in body.items() if k in allowed}
    update["key"] = "reservations"
    await db.app_settings.update_one({"key": "reservations"}, {"$set": update}, upsert=True)
    return await get_reservation_settings()


@api_router.get("/reservations/vehicle-mapping")
async def reservation_vehicle_mapping(user: User = Depends(get_admin_user)):
    names = await db.reservation_drives.distinct("vehicle_name")
    vehicles = await db.vehicles.find(
        {}, {"_id": 0, "vehicle_id": 1, "registration_plate": 1, "brand": 1, "model": 1, "reservation_alias": 1, "auto_created": 1}
    ).to_list(500)
    return {"reservation_vehicle_names": [n for n in names if n], "vehicles": vehicles}

# ---------- ICS (iCalendar) calendar sync ----------
from zoneinfo import ZoneInfo as _ZoneInfo, ZoneInfoNotFoundError

_PRAGUE_TZ = _ZoneInfo("Europe/Prague")


def _ics_unescape(s):
    if s is None:
        return None
    return (s.replace("\\n", "\n").replace("\\N", "\n")
             .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\"))


def _ics_unfold(text):
    """Unfold RFC5545 folded lines (continuation lines start with space or tab)."""
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = []
    for ln in raw:
        if ln[:1] in (" ", "\t") and lines:
            lines[-1] += ln[1:]
        else:
            lines.append(ln)
    return lines


def _parse_ics_events(text):
    events = []
    cur = None
    for ln in _ics_unfold(text):
        if ln == "BEGIN:VEVENT":
            cur = {}
            continue
        if ln == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
            continue
        if cur is None or ":" not in ln:
            continue
        name_part, value = ln.split(":", 1)
        key = name_part.split(";", 1)[0].upper()
        params = {}
        if ";" in name_part:
            for p in name_part.split(";")[1:]:
                if "=" in p:
                    pk, pv = p.split("=", 1)
                    params[pk.upper()] = pv
        cur[key] = {"value": value, "params": params}
    return events


def _parse_ics_dt(field):
    """Return naive UTC datetime from an ICS date-time field dict."""
    if not field:
        return None
    val = field["value"].strip()
    params = field.get("params", {})
    tzid = params.get("TZID")
    try:
        if val.endswith("Z"):
            dt = datetime.strptime(val, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        elif "T" in val:
            naive = datetime.strptime(val, "%Y%m%dT%H%M%S")
            tz = _ZoneInfo(tzid) if tzid else _PRAGUE_TZ
            dt = naive.replace(tzinfo=tz)
        else:
            naive = datetime.strptime(val, "%Y%m%d")
            dt = naive.replace(tzinfo=_PRAGUE_TZ)
    except (ValueError, KeyError, TypeError, ZoneInfoNotFoundError) as exc:
        logger.debug("Nečitelné ICS datum %r: %s", val, exc)
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_ics_summary(summary):
    """SUMMARY like 'Vreštiak (B)\\nParkovani\\n[Ostrov, Učebna]'.
    Returns (customer, activity, boarding_location, note)."""
    text = _ics_unescape(summary) or ""
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    customer = None
    activity = None
    boarding = None
    notes = []
    for i, p in enumerate(parts):
        if p.startswith("[") and p.endswith("]"):
            boarding = p[1:-1].strip()
            continue
        if i == 0:
            m = _re.search(r"\(([^)]*)\)", p)
            if m:
                activity = m.group(1).strip()
                customer = p[:m.start()].strip() or None
            else:
                customer = p
        else:
            low = p.lower()
            if activity is None and any(k in low for k in ("ostatní", "nezapsan", "výcvik", "vycvik")):
                activity = p
            else:
                notes.append(p)
    return customer, activity, _norm_loc(boarding) if boarding else "", ("; ".join(notes) or None)


MAX_ICS_BYTES = 10 * 1024 * 1024


def validate_external_url(url: str) -> str:
    """Validate a user-supplied URL before the server fetches it.

    ICS feed addresses are entered by administrators, and the server fetches
    them itself — an unchecked address turns the backend into a proxy for the
    internal network (SSRF). Only http(s) is allowed, and by default hosts that
    resolve to a loopback, link-local or private address are refused.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"nepodporované schéma URL: {parsed.scheme or 'chybí'}")
    if not parsed.hostname:
        raise ValueError("URL neobsahuje hostitele")

    if settings.ics_allow_private_hosts:
        return url

    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"hostitele {parsed.hostname} se nepodařilo přeložit") from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast):
            raise ValueError(
                f"adresa {address} je v neveřejném rozsahu; "
                "pro interní kalendáře nastavte ICS_ALLOW_PRIVATE_HOSTS=true"
            )
    return url


async def _sync_instructor_ics(instr, settings_doc, cache):
    """Fetch + parse one instructor's ICS feed into reservation_drives."""
    url = (instr or {}).get("ics_url")
    if not url:
        return {"instructor": (instr or {}).get("name"), "events": 0, "error": "chybí ICS URL"}
    try:
        url = validate_external_url(url)
    except ValueError as exc:
        logger.warning("ICS odkaz instruktora %s odmítnut: %s", instr.get("instructor_id"), exc)
        return {"instructor": instr.get("name"), "events": 0, "error": f"neplatný odkaz: {exc}"}

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(20.0, connect=10.0)) as http:
            resp = await http.get(url)
        if resp.status_code != 200:
            logger.warning("ICS feed %s vrátil HTTP %s", instr.get("instructor_id"), resp.status_code)
            return {"instructor": instr.get("name"), "events": 0, "error": f"HTTP {resp.status_code}"}
        if len(resp.content) > MAX_ICS_BYTES:
            return {"instructor": instr.get("name"), "events": 0, "error": "ICS soubor je příliš velký"}
        events = _parse_ics_events(resp.text)
    except httpx.HTTPError as e:
        logger.warning("ICS feed instruktora %s se nepodařilo stáhnout: %s", instr.get("instructor_id"), e)
        return {"instructor": instr.get("name"), "events": 0, "error": str(e)}
    except Exception as e:
        logger.exception("Neočekávaná chyba při ICS synchronizaci instruktora %s", instr.get("instructor_id"))
        return {"instructor": instr.get("name"), "events": 0, "error": str(e)}

    batch_id = f"ics_{instr['instructor_id']}"
    # preserve user-set private flags across re-sync
    old = await db.reservation_drives.find({"batch_id": batch_id}, {"_id": 0, "uid": 1, "is_private": 1}).to_list(20000)
    private_map = {o.get("uid"): o.get("is_private", False) for o in old if o.get("uid")}
    await db.reservation_drives.delete_many({"batch_id": batch_id})

    now = datetime.now(timezone.utc)
    docs = []
    for ev in events:
        start = _parse_ics_dt(ev.get("DTSTART"))
        end = _parse_ics_dt(ev.get("DTEND"))
        if not start:
            continue
        duration_min = int(round((end - start).total_seconds() / 60)) if end else None
        local_start = (start.replace(tzinfo=timezone.utc)).astimezone(_PRAGUE_TZ).replace(tzinfo=None)
        vehicle_name = (ev.get("LOCATION", {}).get("value") or "").strip() or None
        vehicle_id = await _match_or_create_vehicle(vehicle_name, cache) if vehicle_name else None
        customer, activity, boarding, note = _parse_ics_summary(ev.get("SUMMARY", {}).get("value"))
        uid = ev.get("UID", {}).get("value")
        docs.append({
            "drive_id": f"drv_{uuid.uuid4().hex[:12]}",
            "batch_id": batch_id,
            "source": "ics",
            "uid": uid,
            "date": local_start.date().isoformat(),
            "start_datetime": local_start.isoformat(),
            "start_utc": start.isoformat(),
            "hours": round(duration_min / settings_doc.get("minutes_per_hour_unit", 45), 2) if duration_min else None,
            "duration_min": duration_min,
            "teacher": instr.get("name"),
            "instructor_id": instr.get("instructor_id"),
            "vehicle_name": vehicle_name,
            "vehicle_id": vehicle_id,
            "boarding_location": boarding,
            "activity": activity,
            "customer": customer,
            "reservation_km": None,
            "tacho_start": None,
            "tacho_end": None,
            "note": note,
            "is_private": bool(private_map.get(uid, False)),
            "created_at": now.isoformat(),
        })
    if docs:
        await db.reservation_drives.insert_many(docs)
    await db.reservation_batches.update_one(
        {"batch_id": batch_id},
        {"$set": {"batch_id": batch_id, "filename": f"ICS · {instr.get('name')}", "count": len(docs),
                  "skipped": 0, "source": "ics", "instructor_id": instr.get("instructor_id"),
                  "created_at": now.isoformat(), "created_by": "ics-sync"}},
        upsert=True,
    )
    return {"instructor": instr.get("name"), "events": len(docs), "error": None}


_ics_sync_running = False
_ICS_FETCH_DELAY_SEC = 3  # gentle delay between feeds to avoid rate-limiting


async def _run_full_ics_sync(trigger="manual"):
    """Sync all instructors sequentially (gentle) with a delay to avoid rate-limiting."""
    global _ics_sync_running
    _ics_sync_running = True
    started = datetime.now(timezone.utc).isoformat()
    await db.app_settings.update_one(
        {"key": "ics_sync_status"},
        {"$set": {"key": "ics_sync_status", "running": True, "trigger": trigger, "started_at": started}},
        upsert=True,
    )
    try:
        res_settings = await get_reservation_settings()
        instructors = await db.instructors.find({}, {"_id": 0}).to_list(500)
        instructors = [i for i in instructors if i.get("ics_url")]
        cache = {}
        results = []
        for idx, instr in enumerate(instructors):
            results.append(await _sync_instructor_ics(instr, res_settings, cache))
            if idx < len(instructors) - 1:
                await asyncio.sleep(_ICS_FETCH_DELAY_SEC)  # be gentle on the ICS server
        total = sum(r["events"] for r in results)
        await db.app_settings.update_one(
            {"key": "ics_sync_status"},
            {"$set": {"key": "ics_sync_status", "running": False, "last_run": datetime.now(timezone.utc).isoformat(),
                      "trigger": trigger, "synced": len(results), "total_events": total, "results": results}},
            upsert=True,
        )
        return {"synced": len(results), "total_events": total, "results": results}
    finally:
        _ics_sync_running = False
        await db.app_settings.update_one({"key": "ics_sync_status"}, {"$set": {"running": False}}, upsert=True)


@api_router.get("/reservations/ics-status")
async def get_ics_status(user: User = Depends(get_current_user)):
    doc = await db.app_settings.find_one({"key": "ics_sync_status"}, {"_id": 0})
    res_settings = await get_reservation_settings()
    return {
        "auto_sync": res_settings.get("ics_auto_sync", True),
        "interval_minutes": res_settings.get("ics_sync_interval_minutes", 60),
        "running": _ics_sync_running,
        "status": doc,
    }


@api_router.post("/reservations/sync-ics")
async def sync_ics(request: Request, user: User = Depends(get_admin_user)):
    """Trigger ICS sync. Full sync (no instructor_id) runs in background; poll /ics-status.
    Body: {instructor_id?: str}."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    instructor_id = body.get("instructor_id")

    if instructor_id:
        instr = await db.instructors.find_one({"instructor_id": instructor_id}, {"_id": 0})
        if not instr or not instr.get("ics_url"):
            raise HTTPException(status_code=400, detail="Instruktor nemá nastavený ICS odkaz")
        res_settings = await get_reservation_settings()
        res = await _sync_instructor_ics(instr, res_settings, {})
        return {"synced": 1, "total_events": res["events"], "results": [res]}

    # full sync -> background
    if _ics_sync_running:
        return {"started": False, "running": True, "message": "Synchronizace už probíhá"}
    any_url = await db.instructors.count_documents({"ics_url": {"$nin": [None, ""]}})
    if not any_url:
        raise HTTPException(status_code=400, detail="Žádný instruktor nemá nastavený ICS odkaz")
    asyncio.create_task(_run_full_ics_sync("manual"))
    return {"started": True, "running": True, "message": "Synchronizace spuštěna"}


async def ics_auto_sync_loop():
    """Background task: periodically sync ICS calendars."""
    await asyncio.sleep(25)  # let startup settle
    while True:
        interval = 60
        try:
            res_settings = await get_reservation_settings()
            interval = max(5, int(res_settings.get("ics_sync_interval_minutes", 60)))
            if res_settings.get("ics_auto_sync", True):
                summary = await _run_full_ics_sync(trigger="auto")
                logger.info("Auto ICS sync: %d instructors, %d events", summary["synced"], summary["total_events"])
        except Exception as e:
            logger.error("Auto ICS sync error: %s", e)
        await asyncio.sleep(interval * 60)







# ======================== ROOT & HEALTH ========================

@api_router.get("/")
async def root():
    return {"message": "Fleet Management API - Autoškola", "version": app.version}


@api_router.get("/config")
async def get_client_config(user: User = Depends(get_current_user)):
    """Feature flags the UI needs to know about.

    Lets the frontend hide controls that the backend would refuse anyway
    (the demo-data generators), instead of offering a button that 403s.
    """
    return {
        "environment": settings.environment,
        "allow_mock_data": settings.allow_mock_data,
        "teltonika_enabled": settings.teltonika_enabled,
        "teltonika_port": settings.teltonika_port,
        "trip_sources": list(trips_service.REPORTABLE_SOURCES),
    }


@api_router.get("/health")
async def health():
    """Liveness/readiness probe.

    Unauthenticated by design: Docker, Nginx and any external monitor must be
    able to tell a starting container from a broken one without credentials.
    Returns 503 while MongoDB is unreachable so an orchestrator does not send
    traffic to an instance that cannot answer.
    """
    db_ok = await database.ping(timeout=3.0)
    payload = {
        "status": "ok" if db_ok else "degraded",
        "database": "up" if db_ok else "down",
        "teltonika": bool(teltonika_server and teltonika_server.is_running),
        "environment": settings.environment,
        "version": app.version,
    }
    if not db_ok:
        return JSONResponse(status_code=503, content=payload)
    return payload


# Include the router
app.include_router(api_router)

# CORS. The supported deployment serves the frontend and the API from one
# origin through Nginx, where CORS is not involved at all — hence the empty
# default. `allow_origins=["*"]` together with credentials is refused in
# production by the config validation, because it would let any site issue
# authenticated requests on a logged-in user's behalf.
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS povolen pro: %s", ", ".join(settings.cors_origins))


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Baseline response headers for API responses."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the cause, return a generic message.

    An unexpected failure must be diagnosable from the server log, without the
    stack trace being handed to the caller.
    """
    logger.exception("Neošetřená chyba při zpracování %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Interní chyba serveru. Podrobnosti najdete v logu aplikace."},
    )


async def seed_admin():
    """Ensure an administrator account exists.

    The password is only written when the account is created or has no
    password at all. An existing password is left alone unless
    ADMIN_PASSWORD_RESET_ON_START is set explicitly — otherwise every restart
    would silently undo a password an operator had changed.
    """
    if not settings.admin_password:
        logger.warning("ADMIN_PASSWORD není nastaven — administrátorský účet nebude vytvořen.")
        return

    admin_email = settings.admin_email
    existing = await db.users.find_one({"email": admin_email}, {"_id": 0})

    if existing is None:
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": admin_email,
            "name": "Admin",
            "password_hash": hash_password(settings.admin_password),
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info("Administrátorský účet vytvořen: %s", admin_email)
        return

    if not existing.get("password_hash"):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(settings.admin_password)}}
        )
        logger.info("Administrátorskému účtu %s bylo doplněno heslo", admin_email)
        return

    if settings.admin_password_reset_on_start and not verify_password(
        settings.admin_password, existing["password_hash"]
    ):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(settings.admin_password)}}
        )
        logger.info("Heslo administrátora %s bylo obnoveno podle ADMIN_PASSWORD", admin_email)


async def backfill_trip_sources() -> int:
    """Give trips stored before the `source` field existed an explicit source.

    Purely additive: no document is removed or rewritten beyond gaining the
    fields the reporting layer expects. Safe to run on every start.
    """
    try:
        result = await db.gps_trips.update_many(
            {"source": {"$exists": False}},
            {"$set": {"source": trips_service.LEGACY_SOURCE, "duplicate_of": None}},
        )
        if result.modified_count:
            logger.info(
                "Doplněn zdroj u %d historických jízd (%s)",
                result.modified_count, trips_service.LEGACY_SOURCE,
            )
        return result.modified_count
    except PyMongoError as exc:
        logger.warning("Doplnění zdroje jízd se nezdařilo: %s", exc)
        return 0


_background_tasks: List[asyncio.Task] = []


async def startup_tasks():
    """Bring the application up in a defined, observable order.

    Configuration is validated first and fatally: an unsafe production
    configuration must stop the process, not start an application that quietly
    uses a publicly known secret.
    """
    logger.info("Fleet Manager %s se spouští: %s", app.version, settings.safe_summary())

    try:
        settings.validate()
    except ConfigError as exc:
        logger.critical("%s", exc)
        raise

    if not await database.wait_until_ready():
        raise RuntimeError(
            "MongoDB není dostupná. Zkontrolujte MONGO_URL a stav databázového kontejneru."
        )

    await database.ensure_indexes(db)
    await backfill_trip_sources()

    try:
        await seed_admin()
    except PyMongoError:
        logger.exception("Vytvoření administrátorského účtu selhalo")
        raise

    try:
        await start_teltonika_server()
    except OSError as exc:
        logger.error(
            "Teltonika TCP přijímač se nepodařilo spustit na portu %d: %s",
            settings.teltonika_port, exc,
        )

    _background_tasks.append(asyncio.create_task(ics_auto_sync_loop()))
    _background_tasks.append(asyncio.create_task(trip_detection_loop()))
    logger.info("Start dokončen — API je připraveno.")


async def shutdown_tasks():
    """Stop background work before the process exits."""
    for task in _background_tasks:
        task.cancel()
    for task in _background_tasks:
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _background_tasks.clear()

    if teltonika_server:
        await teltonika_server.stop()
    await database.close()
    logger.info("Fleet Manager ukončen.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan: start everything up, then wind it down cleanly."""
    await startup_tasks()
    try:
        yield
    finally:
        await shutdown_tasks()


# Registered after the hooks are defined; `on_event` is deprecated in FastAPI.
app.router.lifespan_context = lifespan
