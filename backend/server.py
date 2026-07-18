from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import io
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import httpx
import base64
import secrets
import bcrypt
import jwt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from teltonika import TeltonikaTCPServer, parse_avl_packet, build_test_avl_packet, build_imei_packet
import resend
import asyncio
import xml.etree.ElementTree as ET
import csv as csv_module

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    assigned_vehicle_ids: List[str] = []
    pin: Optional[str] = None  # 4-6 digit PIN for instructor login

class Instructor(BaseModel):
    model_config = ConfigDict(extra="ignore")
    instructor_id: str
    name: str
    email: str
    phone: str
    license_number: str
    assigned_vehicle_ids: List[str] = []
    pin: Optional[str] = None
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
    created_at: datetime
    updated_at: datetime


# ======================== PASSWORD & JWT HELPERS ========================

JWT_ALGORITHM = "HS256"


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=True, samesite="none", max_age=604800, path="/")


# ======================== HELPERS ========================

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


async def enrich_vehicle_info(doc: dict):
    """Add vehicle_info string to a document that has vehicle_id."""
    vehicle = await db.vehicles.find_one({"vehicle_id": doc["vehicle_id"]}, {"_id": 0})
    if vehicle:
        doc["vehicle_info"] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"


async def enrich_instructor_name(doc: dict):
    """Add instructor_name to a document that has instructor_id."""
    if doc.get("instructor_id"):
        instructor = await db.instructors.find_one({"instructor_id": doc["instructor_id"]}, {"_id": 0})
        if instructor:
            doc["instructor_name"] = instructor["name"]


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
        logger.info("Damage notification email sent to %s", admin_email)
    except Exception as e:
        logger.error("Failed to send damage email: %s", e)


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
    async with httpx.AsyncClient() as http_client:
        auth_response = await http_client.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id}
        )
        if auth_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Neplatný session_id")
        return auth_response.json()


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
        httponly=True,
        secure=True,
        samesite="none",
        max_age=7*24*60*60,
        path="/"
    )

    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return UserResponse(**user_doc)


@api_router.post("/auth/login")
async def admin_login(data: AdminLoginRequest, response: Response):
    """Admin login with email/password"""
    email = data.email.lower().strip()
    user_doc = await db.users.find_one({"email": email}, {"_id": 0})
    if not user_doc or not user_doc.get("password_hash"):
        raise HTTPException(status_code=401, detail="Neplatné přihlašovací údaje")

    if not verify_password(data.password, user_doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Neplatné přihlašovací údaje")

    access = create_access_token(user_doc["user_id"], user_doc.get("role", "admin"))
    refresh = create_refresh_token(user_doc["user_id"])
    _set_auth_cookies(response, access, refresh)

    return {
        "user_id": user_doc["user_id"],
        "email": user_doc["email"],
        "name": user_doc["name"],
        "role": user_doc.get("role", "admin"),
    }


@api_router.post("/auth/instructor-login")
async def instructor_login(data: InstructorLoginRequest, response: Response):
    """Instructor login with ID + PIN"""
    instructor = await db.instructors.find_one(
        {"instructor_id": data.instructor_id}, {"_id": 0}
    )
    if not instructor:
        raise HTTPException(status_code=401, detail="Neplatné přihlašovací údaje")
    if not instructor.get("pin"):
        raise HTTPException(status_code=401, detail="Instruktor nemá nastavený PIN")
    if instructor["pin"] != data.pin:
        raise HTTPException(status_code=401, detail="Neplatný PIN")

    access = create_access_token(instructor["instructor_id"], "instructor")
    refresh = create_refresh_token(instructor["instructor_id"])
    _set_auth_cookies(response, access, refresh)

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

    response.delete_cookie(key="session_token", path="/")
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
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
        response.set_cookie(key="access_token", value=access, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
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

@api_router.get("/instructors", response_model=List[Instructor])
async def get_instructors(user: User = Depends(get_current_user)):
    """Get all instructors"""
    instructors = await db.instructors.find({}, {"_id": 0}).to_list(1000)
    for i in instructors:
        parse_datetime_field(i, "created_at")
        parse_datetime_field(i, "updated_at")
    return instructors

@api_router.get("/instructors/{instructor_id}", response_model=Instructor)
async def get_instructor(instructor_id: str, user: User = Depends(get_current_user)):
    """Get a single instructor"""
    instructor = await db.instructors.find_one({"instructor_id": instructor_id}, {"_id": 0})
    if not instructor:
        raise HTTPException(status_code=404, detail="Instruktor nenalezen")
    parse_datetime_field(instructor, "created_at")
    parse_datetime_field(instructor, "updated_at")
    return Instructor(**instructor)

@api_router.post("/instructors", response_model=Instructor)
async def create_instructor(data: InstructorCreate, user: User = Depends(get_admin_user)):
    """Create a new instructor"""
    instructor_id = f"inst_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    
    instructor = {
        "instructor_id": instructor_id,
        **data.model_dump(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    }
    
    await db.instructors.insert_one(instructor)
    instructor['created_at'] = now
    instructor['updated_at'] = now
    return Instructor(**instructor)

@api_router.put("/instructors/{instructor_id}", response_model=Instructor)
async def update_instructor(instructor_id: str, data: InstructorCreate, user: User = Depends(get_admin_user)):
    """Update an instructor"""
    instructor = await db.instructors.find_one({"instructor_id": instructor_id}, {"_id": 0})
    if not instructor:
        raise HTTPException(status_code=404, detail="Instruktor nenalezen")
    
    now = datetime.now(timezone.utc)
    update_data = {
        **data.model_dump(),
        "updated_at": now.isoformat()
    }
    
    await db.instructors.update_one(
        {"instructor_id": instructor_id},
        {"$set": update_data}
    )
    
    updated = await db.instructors.find_one({"instructor_id": instructor_id}, {"_id": 0})
    parse_datetime_field(updated, "created_at")
    updated['updated_at'] = now
    return Instructor(**updated)

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
    
    entries = await db.logbook.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    
    for entry in entries:
        parse_datetime_field(entry, "created_at")
        await enrich_vehicle_info(entry)
        await enrich_instructor_name(entry)
    
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
        await enrich_vehicle_info(entry)
    
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
        await enrich_vehicle_info(report)
    
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
        await enrich_vehicle_info(protocol)
        await enrich_instructor_name(protocol)
    
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
        await enrich_vehicle_info(h)
    
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
    user: User = Depends(get_current_user)
):
    """Get GPS trips with optional filters"""
    query = {}
    if vehicle_id:
        query["vehicle_id"] = vehicle_id
    
    trips = await db.gps_trips.find(query, {"_id": 0}).sort("start_time", -1).to_list(1000)
    
    for trip in trips:
        parse_datetime_field(trip, "start_time")
        parse_datetime_field(trip, "end_time")
        parse_datetime_field(trip, "created_at")
        await enrich_vehicle_info(trip)
    
    return trips

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
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "start_location": start_loc,
        "end_location": end_loc,
        "route_points": _generate_route_points(start_loc, end_loc, start_time, duration_minutes),
        "distance": distance,
        "max_speed": secrets.randbelow(31) + 50,
        "avg_speed": secrets.randbelow(21) + 25,
        "synced_to_logbook": False,
        "created_at": now.isoformat()
    }


@api_router.post("/gps/import-mock")
async def import_mock_gps_data(vehicle_id: str, user: User = Depends(get_current_user)):
    """Generate mock GPS data for a vehicle (simulating Teltonika FMB003 import)"""
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

    vehicle = await db.vehicles.find_one({"vehicle_id": trip["vehicle_id"]}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    start_time, end_time = _parse_trip_times(trip)
    now = datetime.now(timezone.utc)
    distance_km = trip["distance"] // 1000
    start_odometer = vehicle["odometer"]
    end_odometer = start_odometer + distance_km

    logbook_entry = {
        "entry_id": f"log_{uuid.uuid4().hex[:12]}",
        "vehicle_id": trip["vehicle_id"],
        "instructor_id": vehicle.get("assigned_instructor_id"),
        "date": start_time.strftime("%Y-%m-%d"),
        "start_time": start_time.strftime("%H:%M"),
        "end_time": end_time.strftime("%H:%M"),
        "start_location": trip["start_location"]["address"],
        "end_location": trip["end_location"]["address"],
        "route_description": f"{trip['start_location']['address']} → {trip['end_location']['address']}",
        "start_odometer": start_odometer,
        "end_odometer": end_odometer,
        "distance": distance_km,
        "purpose": "výcvik",
        "notes": f"Import z GPS (max. rychlost: {trip['max_speed']} km/h, prům. rychlost: {trip['avg_speed']} km/h)",
        "gps_source": True,
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

@api_router.get("/reports/dashboard")
async def get_dashboard_stats(user: User = Depends(get_current_user)):
    """Get dashboard statistics"""
    now = datetime.now(timezone.utc)
    
    # Total vehicles
    total_vehicles = await db.vehicles.count_documents({})
    
    # Total instructors
    total_instructors = await db.instructors.count_documents({})
    
    # Total km this month
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    logbook_entries = await db.logbook.find({
        "date": {"$gte": month_start.strftime("%Y-%m-%d")}
    }, {"_id": 0, "distance": 1}).to_list(1000)
    total_km_month = sum(entry.get("distance", 0) for entry in logbook_entries)
    
    # Total fuel cost this month
    fuel_entries = await db.fuel_entries.find({
        "date": {"$gte": month_start.strftime("%Y-%m-%d")}
    }, {"_id": 0, "total_price": 1}).to_list(1000)
    total_fuel_cost_month = sum(entry.get("total_price", 0) for entry in fuel_entries)
    
    # Open damage reports
    open_damages = await db.damage_reports.count_documents({"status": {"$ne": "vyřešeno"}})
    
    # Recent trips (last 7 days)
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    recent_trips = await db.logbook.count_documents({"date": {"$gte": week_ago}})
    
    # Vehicles list with current status
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(100)
    
    return {
        "total_vehicles": total_vehicles,
        "total_instructors": total_instructors,
        "total_km_month": total_km_month,
        "total_fuel_cost_month": round(total_fuel_cost_month, 2),
        "open_damages": open_damages,
        "recent_trips": recent_trips,
        "vehicles": vehicles
    }

@api_router.get("/reports/km-stats")
async def get_km_statistics(
    date_from: str,
    date_to: str,
    vehicle_id: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Get kilometer statistics for a date range"""
    query = {
        "date": {"$gte": date_from, "$lte": date_to}
    }
    if vehicle_id:
        query["vehicle_id"] = vehicle_id
    
    entries = await db.logbook.find(query, {"_id": 0}).to_list(10000)
    
    # Group by date
    daily_stats = {}
    vehicle_stats = {}
    
    for entry in entries:
        date = entry["date"]
        distance = entry.get("distance", 0)
        vid = entry["vehicle_id"]
        
        if date not in daily_stats:
            daily_stats[date] = 0
        daily_stats[date] += distance
        
        if vid not in vehicle_stats:
            vehicle_stats[vid] = {"total_km": 0, "trips": 0}
        vehicle_stats[vid]["total_km"] += distance
        vehicle_stats[vid]["trips"] += 1
    
    # Enrich vehicle stats with names
    for vid in vehicle_stats:
        vehicle = await db.vehicles.find_one({"vehicle_id": vid}, {"_id": 0})
        if vehicle:
            vehicle_stats[vid]["name"] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    
    total_km = sum(daily_stats.values())
    num_days = len(daily_stats) if daily_stats else 1
    
    return {
        "total_km": total_km,
        "avg_km_per_day": round(total_km / num_days, 1),
        "daily_stats": [{"date": k, "km": v} for k, v in sorted(daily_stats.items())],
        "vehicle_stats": vehicle_stats
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
        source = "GPS" if e.get("gps_source") else "Man."
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


@api_router.get("/logbook/export-pdf")
async def export_logbook_pdf(
    vehicle_id: Optional[str] = None,
    instructor_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """Export logbook entries as a PDF file"""
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

    entries = await db.logbook.find(query, {"_id": 0}).sort("date", 1).to_list(10000)

    for entry in entries:
        await enrich_vehicle_info(entry)
        await enrich_instructor_name(entry)

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
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(100)
    positions = []

    for v in vehicles:
        pos = await db.vehicle_positions.find_one(
            {"vehicle_id": v["vehicle_id"]}, {"_id": 0}, sort=[("timestamp", -1)]
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
async def simulate_live_positions(user: User = Depends(get_current_user)):
    """Generate simulated live position updates for all vehicles (mock real-time)."""
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


async def on_teltonika_records(imei: str, records: list):
    """Callback invoked by the TCP server when AVL records arrive."""
    device = await db.gps_devices.find_one({"imei": imei}, {"_id": 0})
    if not device:
        logger.warning("Unknown IMEI: %s — data discarded", imei)
        return

    vehicle_id = device["vehicle_id"]
    now = datetime.now(timezone.utc)

    for rec in records:
        gps = rec["gps"]
        if gps["lat"] == 0.0 and gps["lng"] == 0.0:
            continue  # skip invalid GPS fix

        obd = rec.get("obd", {})

        position_doc = {
            "vehicle_id": vehicle_id,
            "lat": gps["lat"],
            "lng": gps["lng"],
            "speed": gps["speed"],
            "heading": gps["angle"],
            "altitude": gps.get("altitude", 0),
            "satellites": gps.get("satellites", 0),
            "ignition": obd.get("ignition", {}).get("value", gps["speed"] > 0),
            "source": "teltonika",
            "imei": imei,
            "timestamp": rec["timestamp"].isoformat(),
        }

        # Add OBD data if present
        if obd:
            position_doc["obd"] = {k: v["value"] for k, v in obd.items()}

        await db.vehicle_positions.insert_one(position_doc)

        # Store OBD snapshot for diagnostics
        if obd:
            await db.vehicle_obd.update_one(
                {"vehicle_id": vehicle_id},
                {"$set": {
                    "vehicle_id": vehicle_id,
                    "imei": imei,
                    "data": {k: v for k, v in obd.items()},
                    "timestamp": rec["timestamp"].isoformat(),
                    "updated_at": now.isoformat(),
                }},
                upsert=True,
            )

    await db.gps_devices.update_one(
        {"imei": imei},
        {"$set": {"last_seen": now.isoformat(), "status": "online"}}
    )


async def start_teltonika_server():
    """Start the Teltonika TCP server as a background task."""
    global teltonika_server
    port = int(os.environ.get("TELTONIKA_TCP_PORT", "5027"))
    teltonika_server = TeltonikaTCPServer(host="0.0.0.0", port=port, on_records=on_teltonika_records)
    await teltonika_server.start()


# ── Device management endpoints ──

@api_router.get("/gps/devices")
async def get_gps_devices(user: User = Depends(get_current_user)):
    """List all registered GPS tracker devices."""
    devices = await db.gps_devices.find({}, {"_id": 0}).to_list(100)
    for d in devices:
        parse_datetime_field(d, "created_at")
        parse_datetime_field(d, "last_seen")
        await enrich_vehicle_info(d)
    return devices


@api_router.post("/gps/devices")
async def register_gps_device(data: GPSDeviceCreate, user: User = Depends(get_current_user)):
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
async def delete_gps_device(device_id: str, user: User = Depends(get_current_user)):
    """Unregister a GPS tracker device."""
    result = await db.gps_devices.delete_one({"device_id": device_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Zařízení nenalezeno")
    return {"message": "Zařízení odstraněno"}


@api_router.get("/gps/tcp-status")
async def get_tcp_status(user: User = Depends(get_current_user)):
    """Get Teltonika TCP server status."""
    if teltonika_server:
        return teltonika_server.stats
    return {"running": False, "host": "0.0.0.0", "port": 5027, "active_connections": 0, "total_records_received": 0}


@api_router.post("/gps/test-teltonika")
async def test_teltonika_device(
    imei: str,
    lat: float = 50.0755,
    lng: float = 14.4378,
    speed: int = 45,
    user: User = Depends(get_current_user)
):
    """Simulate a Teltonika device sending a single AVL record (for testing without hardware)."""
    import asyncio as _asyncio

    port = int(os.environ.get("TELTONIKA_TCP_PORT", "5027"))

    try:
        reader, writer = await _asyncio.open_connection("127.0.0.1", port)

        # Send IMEI
        writer.write(build_imei_packet(imei))
        await writer.drain()
        resp = await reader.read(1)
        if resp != b"\x01":
            writer.close()
            return {"success": False, "error": "IMEI rejected"}

        # Send AVL packet
        packet = build_test_avl_packet(lat=lat, lng=lng, speed=speed)
        writer.write(packet)
        await writer.drain()
        ack = await reader.read(4)

        import struct as _struct
        ack_count = _struct.unpack(">I", ack)[0] if len(ack) == 4 else 0
        writer.close()

        return {"success": True, "records_acked": ack_count, "imei": imei, "lat": lat, "lng": lng, "speed": speed}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ======================== OBD-II DIAGNOSTICS ========================

@api_router.get("/obd/vehicles")
async def get_all_obd_data(user: User = Depends(get_current_user)):
    """Get latest OBD-II diagnostic data for all vehicles."""
    obd_docs = await db.vehicle_obd.find({}, {"_id": 0}).to_list(100)
    for doc in obd_docs:
        await enrich_vehicle_info(doc)
        parse_datetime_field(doc, "timestamp")
        parse_datetime_field(doc, "updated_at")
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

def _build_trip_doc(vehicle_id: str, trip_start: dict, trip_points: list) -> dict:
    """Build a trip document from detected trip start and points."""
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


@api_router.post("/gps/detect-trips/{vehicle_id}")
async def detect_trips_from_positions(vehicle_id: str, user: User = Depends(get_current_user)):
    """Detect trips from position history using ignition on/off transitions."""
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    positions = await db.vehicle_positions.find(
        {"vehicle_id": vehicle_id}, {"_id": 0}
    ).sort("timestamp", 1).to_list(50000)

    if len(positions) < 2:
        return {"message": "Nedostatek dat pro detekci jízd", "trips": 0}

    trips_created = 0
    trip_start = None
    trip_points = []

    for pos in positions:
        ts = pos.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        ignition = pos.get("ignition", pos.get("speed", 0) > 0)

        if ignition and trip_start is None:
            trip_start = {"time": ts, "lat": pos["lat"], "lng": pos["lng"]}
            trip_points = [pos]
        elif ignition and trip_start is not None:
            trip_points.append(pos)
        elif not ignition and trip_start is not None and len(trip_points) >= 2:
            trip_doc, distance = _build_trip_doc(vehicle_id, trip_start, trip_points)
            if distance >= 100:
                await db.gps_trips.insert_one(trip_doc)
                trips_created += 1
            trip_start = None
            trip_points = []

    return {"message": f"Detekováno {trips_created} jízd", "trips": trips_created}


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
    results = []
    for item in items:
        parse_datetime_field(item, "created_at")
        parse_datetime_field(item, "updated_at")
        await enrich_vehicle_info(item)
        item["status"] = compute_maintenance_status(item)
        if status and item["status"] != status:
            continue
        results.append(MaintenanceItem(**item))
    return results


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
    return {"message": "Záznam údržby smazán"}


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


# ======================== RUHAVIK IMPORT ROUTES ========================

def _parse_gpx_file(content: str) -> list:
    """Parse GPX file and extract track points."""
    points = []
    try:
        root = ET.fromstring(content)
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        # Try standard GPX 1.1 namespace
        trkpts = root.findall(".//gpx:trkpt", ns)
        if not trkpts:
            # Try without namespace
            trkpts = root.findall(".//{http://www.topografix.com/GPX/1/1}trkpt")
        if not trkpts:
            trkpts = root.findall(".//trkpt")
        for pt in trkpts:
            lat = float(pt.get("lat", 0))
            lng = float(pt.get("lon", 0))
            time_el = pt.find("gpx:time", ns) or pt.find("{http://www.topografix.com/GPX/1/1}time") or pt.find("time")
            speed_el = pt.find("gpx:speed", ns) or pt.find("{http://www.topografix.com/GPX/1/1}speed") or pt.find("speed")
            timestamp = time_el.text if time_el is not None else None
            speed = float(speed_el.text) * 3.6 if speed_el is not None else 0  # m/s -> km/h
            if lat and lng:
                points.append({"lat": lat, "lng": lng, "timestamp": timestamp, "speed": speed})
    except ET.ParseError as e:
        logger.error("GPX parse error: %s", e)
    return points


def _parse_csv_ruhavik(content: str) -> list:
    """Parse Ruhavik CSV export. Columns: timestamp, lat, lng, speed, ..."""
    points = []
    reader = csv_module.DictReader(io.StringIO(content))
    field_map = {}
    if reader.fieldnames:
        lower_fields = {f.lower().strip(): f for f in reader.fieldnames}
        for key in ["latitude", "lat"]:
            if key in lower_fields:
                field_map["lat"] = lower_fields[key]
                break
        for key in ["longitude", "lng", "lon"]:
            if key in lower_fields:
                field_map["lng"] = lower_fields[key]
                break
        for key in ["time", "timestamp", "datetime", "date"]:
            if key in lower_fields:
                field_map["time"] = lower_fields[key]
                break
        for key in ["speed", "velocity"]:
            if key in lower_fields:
                field_map["speed"] = lower_fields[key]
                break
    for row in reader:
        try:
            lat = float(row.get(field_map.get("lat", "latitude"), 0))
            lng = float(row.get(field_map.get("lng", "longitude"), 0))
            timestamp = row.get(field_map.get("time", "timestamp"), "")
            speed = float(row.get(field_map.get("speed", "speed"), 0) or 0)
            if lat and lng:
                points.append({"lat": lat, "lng": lng, "timestamp": timestamp, "speed": speed})
        except (ValueError, TypeError):
            continue
    return points


def _points_to_trips(points: list, vehicle_id: str, min_gap_minutes: int = 15) -> list:
    """Split sorted points into trips based on time gaps."""
    if not points:
        return []
    # Sort by timestamp
    valid_points = [p for p in points if p.get("timestamp")]
    if not valid_points:
        # If no timestamps, create one trip from all points
        now = datetime.now(timezone.utc)
        return [{
            "trip_id": f"gps_{uuid.uuid4().hex[:12]}",
            "vehicle_id": vehicle_id,
            "start_time": now.isoformat(),
            "end_time": now.isoformat(),
            "start_location": {"lat": points[0]["lat"], "lng": points[0]["lng"], "address": f"{points[0]['lat']:.4f}, {points[0]['lng']:.4f}"},
            "end_location": {"lat": points[-1]["lat"], "lng": points[-1]["lng"], "address": f"{points[-1]['lat']:.4f}, {points[-1]['lng']:.4f}"},
            "route_points": [{"lat": p["lat"], "lng": p["lng"], "timestamp": now.isoformat()} for p in points],
            "distance": 0,
            "max_speed": int(max((p.get("speed", 0) for p in points), default=0)),
            "avg_speed": int(sum(p.get("speed", 0) for p in points) / len(points)) if points else 0,
            "synced_to_logbook": False,
            "created_at": now.isoformat()
        }]
    valid_points.sort(key=lambda p: p["timestamp"])
    trips = []
    current_trip_points = [valid_points[0]]
    for i in range(1, len(valid_points)):
        try:
            prev_t = datetime.fromisoformat(valid_points[i - 1]["timestamp"].replace("Z", "+00:00"))
            curr_t = datetime.fromisoformat(valid_points[i]["timestamp"].replace("Z", "+00:00"))
            gap = (curr_t - prev_t).total_seconds() / 60
        except (ValueError, TypeError):
            gap = 0
        if gap > min_gap_minutes:
            trips.append(current_trip_points)
            current_trip_points = []
        current_trip_points.append(valid_points[i])
    if current_trip_points:
        trips.append(current_trip_points)

    now = datetime.now(timezone.utc)
    result = []
    for trip_pts in trips:
        if len(trip_pts) < 2:
            continue
        start = trip_pts[0]
        end = trip_pts[-1]
        speeds = [p.get("speed", 0) for p in trip_pts]
        # Estimate distance using Haversine approximation
        total_dist = 0
        for j in range(1, len(trip_pts)):
            dlat = (trip_pts[j]["lat"] - trip_pts[j - 1]["lat"]) * 111320
            dlng = (trip_pts[j]["lng"] - trip_pts[j - 1]["lng"]) * 111320 * 0.65
            total_dist += (dlat ** 2 + dlng ** 2) ** 0.5
        result.append({
            "trip_id": f"gps_{uuid.uuid4().hex[:12]}",
            "vehicle_id": vehicle_id,
            "start_time": start["timestamp"],
            "end_time": end["timestamp"],
            "start_location": {"lat": start["lat"], "lng": start["lng"], "address": f"{start['lat']:.4f}, {start['lng']:.4f}"},
            "end_location": {"lat": end["lat"], "lng": end["lng"], "address": f"{end['lat']:.4f}, {end['lng']:.4f}"},
            "route_points": [{"lat": p["lat"], "lng": p["lng"], "timestamp": p["timestamp"]} for p in trip_pts],
            "distance": int(total_dist),
            "max_speed": int(max(speeds, default=0)),
            "avg_speed": int(sum(speeds) / len(speeds)) if speeds else 0,
            "synced_to_logbook": False,
            "created_at": now.isoformat()
        })
    return result


@api_router.post("/gps/import-ruhavik")
async def import_ruhavik_data(
    vehicle_id: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user)
):
    """Import GPS data from Ruhavik CSV or GPX file"""
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    content = (await file.read()).decode("utf-8", errors="ignore")
    filename = (file.filename or "").lower()

    points = []
    if filename.endswith(".gpx"):
        points = _parse_gpx_file(content)
    elif filename.endswith(".csv"):
        points = _parse_csv_ruhavik(content)
    else:
        raise HTTPException(status_code=400, detail="Nepodporovaný formát. Nahrajte .csv nebo .gpx soubor.")

    if not points:
        raise HTTPException(status_code=400, detail="Soubor neobsahuje žádné platné GPS body.")

    trips = _points_to_trips(points, vehicle_id)

    for trip in trips:
        await db.gps_trips.insert_one(trip)

    return {
        "message": f"Importováno {len(trips)} tras z {len(points)} bodů",
        "trips_count": len(trips),
        "points_count": len(points),
        "trip_ids": [t["trip_id"] for t in trips]
    }


# ======================== UPLOAD & ROOT ========================

@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Upload a file and return base64 data URL"""
    content = await file.read()
    base64_content = base64.b64encode(content).decode('utf-8')
    content_type = file.content_type or 'image/jpeg'
    data_url = f"data:{content_type};base64,{base64_content}"
    return {"url": data_url, "filename": file.filename}

@api_router.post("/public/upload")
async def public_upload_file(file: UploadFile = File(...)):
    """Upload a file (public endpoint for QR flows)"""
    content = await file.read()
    base64_content = base64.b64encode(content).decode('utf-8')
    content_type = file.content_type or 'image/jpeg'
    data_url = f"data:{content_type};base64,{base64_content}"
    return {"url": data_url, "filename": file.filename}

# ======================== ROOT ========================

@api_router.get("/")
async def root():
    return {"message": "Fleet Management API - Autoškola"}

# Include the router
app.include_router(api_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

async def seed_admin():
    """Seed admin user on startup."""
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@autoskola.cz").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin123!")
    existing = await db.users.find_one({"email": admin_email}, {"_id": 0})
    if existing is None:
        hashed = hash_password(admin_password)
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": admin_email,
            "name": "Admin",
            "password_hash": hashed,
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info("Admin account seeded: %s", admin_email)
    elif not existing.get("password_hash"):
        hashed = hash_password(admin_password)
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hashed}}
        )
        logger.info("Admin password_hash added to existing account: %s", admin_email)
    elif not verify_password(admin_password, existing["password_hash"]):
        hashed = hash_password(admin_password)
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hashed}}
        )
        logger.info("Admin password updated: %s", admin_email)


@app.on_event("startup")
async def startup_tasks():
    try:
        await seed_admin()
        await start_teltonika_server()
        logger.info("Startup complete: admin seeded, Teltonika TCP started")
    except Exception as e:
        logger.error("Startup error: %s", e)


@app.on_event("shutdown")
async def shutdown_db_client():
    if teltonika_server:
        await teltonika_server.stop()
    client.close()
