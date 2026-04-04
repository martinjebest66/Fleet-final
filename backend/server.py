from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Form
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import httpx
import base64
import random

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

class Instructor(BaseModel):
    model_config = ConfigDict(extra="ignore")
    instructor_id: str
    name: str
    email: str
    phone: str
    license_number: str
    assigned_vehicle_ids: List[str] = []
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

# ======================== AUTH HELPERS ========================

async def get_current_user(request: Request) -> User:
    """Get current user from session token - REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ")[1]
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Nepřihlášen")
    
    session_doc = await db.user_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )
    
    if not session_doc:
        raise HTTPException(status_code=401, detail="Neplatná relace")
    
    expires_at = session_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Relace vypršela")
    
    user_doc = await db.users.find_one(
        {"user_id": session_doc["user_id"]},
        {"_id": 0}
    )
    
    if not user_doc:
        raise HTTPException(status_code=401, detail="Uživatel nenalezen")
    
    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    
    return User(**user_doc)

# ======================== AUTH ROUTES ========================

@api_router.post("/auth/session")
async def process_session(request: Request, response: Response):
    """Process session_id from Emergent Auth and establish session"""
    data = await request.json()
    session_id = data.get("session_id")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="Chybí session_id")
    
    # Call Emergent Auth to get session data
    async with httpx.AsyncClient() as client:
        auth_response = await client.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id}
        )
        
        if auth_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Neplatný session_id")
        
        session_data = auth_response.json()
    
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    email = session_data["email"]
    
    # Check if user exists
    existing_user = await db.users.find_one({"email": email}, {"_id": 0})
    
    if existing_user:
        user_id = existing_user["user_id"]
        # Update user data
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "name": session_data["name"],
                "picture": session_data.get("picture"),
            }}
        )
    else:
        # Create new user
        new_user = {
            "user_id": user_id,
            "email": email,
            "name": session_data["name"],
            "picture": session_data.get("picture"),
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(new_user)
    
    # Create session
    session_token = session_data["session_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=7*24*60*60,
        path="/"
    )
    
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return UserResponse(**user_doc)

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get current authenticated user"""
    return UserResponse(**user.model_dump())

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout user and clear session"""
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_many({"session_token": session_token})
    
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Odhlášeno"}

# ======================== VEHICLE ROUTES ========================

@api_router.get("/vehicles", response_model=List[Vehicle])
async def get_vehicles(user: User = Depends(get_current_user)):
    """Get all vehicles"""
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(1000)
    for v in vehicles:
        if isinstance(v.get('created_at'), str):
            v['created_at'] = datetime.fromisoformat(v['created_at'])
        if isinstance(v.get('updated_at'), str):
            v['updated_at'] = datetime.fromisoformat(v['updated_at'])
        # Add qr_code_handover if missing (for existing vehicles)
        if not v.get('qr_code_handover'):
            v['qr_code_handover'] = f"handover_{v['vehicle_id']}"
    return vehicles

@api_router.get("/vehicles/{vehicle_id}", response_model=Vehicle)
async def get_vehicle(vehicle_id: str, user: User = Depends(get_current_user)):
    """Get a single vehicle"""
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    if isinstance(vehicle.get('created_at'), str):
        vehicle['created_at'] = datetime.fromisoformat(vehicle['created_at'])
    if isinstance(vehicle.get('updated_at'), str):
        vehicle['updated_at'] = datetime.fromisoformat(vehicle['updated_at'])
    # Add qr_code_handover if missing
    if not vehicle.get('qr_code_handover'):
        vehicle['qr_code_handover'] = f"handover_{vehicle['vehicle_id']}"
    return Vehicle(**vehicle)

@api_router.post("/vehicles", response_model=Vehicle)
async def create_vehicle(data: VehicleCreate, user: User = Depends(get_current_user)):
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
async def update_vehicle(vehicle_id: str, data: VehicleCreate, user: User = Depends(get_current_user)):
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
    if isinstance(updated.get('created_at'), str):
        updated['created_at'] = datetime.fromisoformat(updated['created_at'])
    updated['updated_at'] = now
    return Vehicle(**updated)

@api_router.delete("/vehicles/{vehicle_id}")
async def delete_vehicle(vehicle_id: str, user: User = Depends(get_current_user)):
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
        if isinstance(i.get('created_at'), str):
            i['created_at'] = datetime.fromisoformat(i['created_at'])
        if isinstance(i.get('updated_at'), str):
            i['updated_at'] = datetime.fromisoformat(i['updated_at'])
    return instructors

@api_router.get("/instructors/{instructor_id}", response_model=Instructor)
async def get_instructor(instructor_id: str, user: User = Depends(get_current_user)):
    """Get a single instructor"""
    instructor = await db.instructors.find_one({"instructor_id": instructor_id}, {"_id": 0})
    if not instructor:
        raise HTTPException(status_code=404, detail="Instruktor nenalezen")
    if isinstance(instructor.get('created_at'), str):
        instructor['created_at'] = datetime.fromisoformat(instructor['created_at'])
    if isinstance(instructor.get('updated_at'), str):
        instructor['updated_at'] = datetime.fromisoformat(instructor['updated_at'])
    return Instructor(**instructor)

@api_router.post("/instructors", response_model=Instructor)
async def create_instructor(data: InstructorCreate, user: User = Depends(get_current_user)):
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
async def update_instructor(instructor_id: str, data: InstructorCreate, user: User = Depends(get_current_user)):
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
    if isinstance(updated.get('created_at'), str):
        updated['created_at'] = datetime.fromisoformat(updated['created_at'])
    updated['updated_at'] = now
    return Instructor(**updated)

@api_router.delete("/instructors/{instructor_id}")
async def delete_instructor(instructor_id: str, user: User = Depends(get_current_user)):
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
    
    # Enrich with vehicle and instructor info
    for entry in entries:
        if isinstance(entry.get('created_at'), str):
            entry['created_at'] = datetime.fromisoformat(entry['created_at'])
        
        vehicle = await db.vehicles.find_one({"vehicle_id": entry["vehicle_id"]}, {"_id": 0})
        if vehicle:
            entry['vehicle_info'] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
        
        if entry.get('instructor_id'):
            instructor = await db.instructors.find_one({"instructor_id": entry["instructor_id"]}, {"_id": 0})
            if instructor:
                entry['instructor_name'] = instructor['name']
    
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
    
    # Enrich response
    vehicle = await db.vehicles.find_one({"vehicle_id": data.vehicle_id}, {"_id": 0})
    if vehicle:
        entry['vehicle_info'] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    
    if data.instructor_id:
        instructor = await db.instructors.find_one({"instructor_id": data.instructor_id}, {"_id": 0})
        if instructor:
            entry['instructor_name'] = instructor['name']
    
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
        if isinstance(entry.get('created_at'), str):
            entry['created_at'] = datetime.fromisoformat(entry['created_at'])
        
        vehicle = await db.vehicles.find_one({"vehicle_id": entry["vehicle_id"]}, {"_id": 0})
        if vehicle:
            entry['vehicle_info'] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    
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
    
    vehicle = await db.vehicles.find_one({"vehicle_id": data.vehicle_id}, {"_id": 0})
    if vehicle:
        entry['vehicle_info'] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    
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
        if isinstance(report.get('created_at'), str):
            report['created_at'] = datetime.fromisoformat(report['created_at'])
        if isinstance(report.get('resolved_at'), str):
            report['resolved_at'] = datetime.fromisoformat(report['resolved_at'])
        
        vehicle = await db.vehicles.find_one({"vehicle_id": report["vehicle_id"]}, {"_id": 0})
        if vehicle:
            report['vehicle_info'] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    
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
    
    vehicle = await db.vehicles.find_one({"vehicle_id": data.vehicle_id}, {"_id": 0})
    if vehicle:
        report['vehicle_info'] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    
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
        if isinstance(protocol.get('created_at'), str):
            protocol['created_at'] = datetime.fromisoformat(protocol['created_at'])
        
        vehicle = await db.vehicles.find_one({"vehicle_id": protocol["vehicle_id"]}, {"_id": 0})
        if vehicle:
            protocol['vehicle_info'] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
        
        instructor = await db.instructors.find_one({"instructor_id": protocol["instructor_id"]}, {"_id": 0})
        if instructor:
            protocol['instructor_name'] = instructor['name']
    
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
    
    vehicle = await db.vehicles.find_one({"vehicle_id": data.vehicle_id}, {"_id": 0})
    if vehicle:
        protocol['vehicle_info'] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    
    instructor = await db.instructors.find_one({"instructor_id": data.instructor_id}, {"_id": 0})
    if instructor:
        protocol['instructor_name'] = instructor['name']
    
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
        if isinstance(h.get('created_at'), str):
            h['created_at'] = datetime.fromisoformat(h['created_at'])
        
        vehicle = await db.vehicles.find_one({"vehicle_id": h["vehicle_id"]}, {"_id": 0})
        if vehicle:
            h['vehicle_info'] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    
    return handovers

@api_router.get("/qr-handovers/{qr_handover_id}")
async def get_qr_handover(qr_handover_id: str, user: User = Depends(get_current_user)):
    """Get a single QR handover protocol"""
    handover = await db.qr_handovers.find_one({"qr_handover_id": qr_handover_id}, {"_id": 0})
    if not handover:
        raise HTTPException(status_code=404, detail="Předávací protokol nenalezen")
    
    if isinstance(handover.get('created_at'), str):
        handover['created_at'] = datetime.fromisoformat(handover['created_at'])
    
    vehicle = await db.vehicles.find_one({"vehicle_id": handover["vehicle_id"]}, {"_id": 0})
    if vehicle:
        handover['vehicle_info'] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    
    return handover

# Public endpoint for QR handover submission
@api_router.post("/public/qr-handover")
async def create_public_qr_handover(data: QRHandoverCreate):
    """Create QR handover protocol via QR code (public endpoint for mobile)"""
    vehicle = await db.vehicles.find_one({"vehicle_id": data.vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Validate that all 6 required photos are provided
    required_photo_types = {"front", "rear", "left", "right", "interior", "dashboard"}
    provided_photo_types = {p.photo_type for p in data.photos}
    
    if provided_photo_types != required_photo_types:
        missing = required_photo_types - provided_photo_types
        raise HTTPException(status_code=400, detail=f"Chybí požadované fotografie: {', '.join(missing)}")
    
    # Validate fluid checks - all must be checked
    if not all([
        data.fluid_checks.engine_oil,
        data.fluid_checks.coolant,
        data.fluid_checks.brake_fluid,
        data.fluid_checks.windshield_washer,
        data.fluid_checks.other_fluids
    ]):
        raise HTTPException(status_code=400, detail="Všechny provozní kapaliny musí být zkontrolovány")
    
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
    
    # Update vehicle odometer
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
        if isinstance(trip.get('start_time'), str):
            trip['start_time'] = datetime.fromisoformat(trip['start_time'])
        if isinstance(trip.get('end_time'), str):
            trip['end_time'] = datetime.fromisoformat(trip['end_time'])
        if isinstance(trip.get('created_at'), str):
            trip['created_at'] = datetime.fromisoformat(trip['created_at'])
        
        vehicle = await db.vehicles.find_one({"vehicle_id": trip["vehicle_id"]}, {"_id": 0})
        if vehicle:
            trip['vehicle_info'] = f"{vehicle['brand']} {vehicle['model']} ({vehicle['registration_plate']})"
    
    return trips

@api_router.post("/gps/import-mock")
async def import_mock_gps_data(vehicle_id: str, user: User = Depends(get_current_user)):
    """Generate mock GPS data for a vehicle (simulating Teltonika FMB003 import)"""
    vehicle = await db.vehicles.find_one({"vehicle_id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Generate mock trips for the last 7 days
    trips_created = []
    now = datetime.now(timezone.utc)
    
    # Sample Czech locations for driving school
    locations = [
        {"lat": 50.0755, "lng": 14.4378, "address": "Praha, Václavské náměstí"},
        {"lat": 50.0880, "lng": 14.4208, "address": "Praha, Letná"},
        {"lat": 50.0663, "lng": 14.3782, "address": "Praha, Smíchov"},
        {"lat": 50.1010, "lng": 14.4000, "address": "Praha, Kobylisy"},
        {"lat": 50.0500, "lng": 14.4600, "address": "Praha, Vršovice"},
        {"lat": 50.0800, "lng": 14.5000, "address": "Praha, Žižkov"},
    ]
    
    for day_offset in range(7):
        # 1-3 trips per day
        num_trips = random.randint(1, 3)
        for trip_num in range(num_trips):
            trip_date = now - timedelta(days=day_offset)
            start_hour = 8 + trip_num * 3
            
            start_time = trip_date.replace(hour=start_hour, minute=random.randint(0, 30))
            duration_minutes = random.randint(30, 90)
            end_time = start_time + timedelta(minutes=duration_minutes)
            
            start_loc = random.choice(locations)
            end_loc = random.choice([l for l in locations if l != start_loc])
            
            distance = random.randint(5000, 25000)  # 5-25 km in meters
            
            # Generate route points
            num_points = random.randint(10, 30)
            route_points = []
            for i in range(num_points):
                progress = i / num_points
                lat = start_loc["lat"] + (end_loc["lat"] - start_loc["lat"]) * progress + random.uniform(-0.005, 0.005)
                lng = start_loc["lng"] + (end_loc["lng"] - start_loc["lng"]) * progress + random.uniform(-0.005, 0.005)
                point_time = start_time + timedelta(minutes=int(duration_minutes * progress))
                route_points.append({
                    "lat": lat,
                    "lng": lng,
                    "timestamp": point_time.isoformat()
                })
            
            trip_id = f"gps_{uuid.uuid4().hex[:12]}"
            trip = {
                "trip_id": trip_id,
                "vehicle_id": vehicle_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "start_location": start_loc,
                "end_location": end_loc,
                "route_points": route_points,
                "distance": distance,
                "max_speed": random.randint(50, 80),
                "avg_speed": random.randint(25, 45),
                "synced_to_logbook": False,
                "created_at": now.isoformat()
            }
            
            await db.gps_trips.insert_one(trip)
            trips_created.append(trip_id)
    
    return {"message": f"Importováno {len(trips_created)} GPS záznamů", "trip_ids": trips_created}

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
    
    start_time = datetime.fromisoformat(trip["start_time"]) if isinstance(trip["start_time"], str) else trip["start_time"]
    end_time = datetime.fromisoformat(trip["end_time"]) if isinstance(trip["end_time"], str) else trip["end_time"]
    
    entry_id = f"log_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    
    distance_km = trip["distance"] // 1000
    start_odometer = vehicle["odometer"]
    end_odometer = start_odometer + distance_km
    
    logbook_entry = {
        "entry_id": entry_id,
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
    
    # Update trip as synced
    await db.gps_trips.update_one(
        {"trip_id": trip_id},
        {"$set": {"synced_to_logbook": True}}
    )
    
    # Update vehicle odometer
    await db.vehicles.update_one(
        {"vehicle_id": trip["vehicle_id"]},
        {"$set": {"odometer": end_odometer, "updated_at": now.isoformat()}}
    )
    
    return {"message": "Záznam synchronizován do knihy jízd", "entry_id": entry_id}

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

# ======================== FILE UPLOAD ========================

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

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
