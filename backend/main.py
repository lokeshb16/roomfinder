import os
import time
import asyncio
import hashlib
from typing import List, Optional
from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from bson import ObjectId

class UserSignup(BaseModel):
    username: str
    password: str

# 1. SETUP & CONFIGURATION
load_dotenv()
MONGO_URL = os.getenv("MONGO_URL") or os.getenv("MONGO_URI") or "mongodb://localhost:27017"

app = FastAPI(title="RoomFinder API", description="Hyperlocal No-Brokerage Room Rental Platform")

# CORS Setup (To allow frontend connection with the backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Note: Restrict this to specific domains in production environments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uploads folder setup to serve images/videos directly to the browser
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# 2. DATABASE CONNECTIVITY (with timeouts to prevent infinite hangs)
print(f"Connecting to MongoDB: {MONGO_URL[:25]}..." if len(MONGO_URL) > 25 else f"Connecting to MongoDB: {MONGO_URL}")
client = AsyncIOMotorClient(
    MONGO_URL,
    serverSelectionTimeoutMS=5000,   # Fail in 5s if server unreachable
    connectTimeoutMS=5000,           # Fail in 5s if connection can't be made
    socketTimeoutMS=10000            # Fail in 10s if a socket operation stalls
)
db = client["roomfinder_db"]

@app.on_event("startup")
async def startup_db_client():
    async def init_db_indexes():
        try:
            # Quick ping to verify MongoDB is reachable
            await client.admin.command('ping')
            print("MongoDB PING successful — database is reachable!")
            
            # Create a 2dsphere index for high-speed geospatial location lookups
            await db["rooms"].create_index([("location", "2dsphere")])
            
            # Initialize counter for global stats if it doesn't exist yet
            counter = await db["counters"].find_one({"_id": "room_counter"})
            if not counter:
                await db["counters"].insert_one({"_id": "room_counter", "count": 0})
                
            print("MongoDB connected, 2dsphere index ensured successfully!")
        except Exception as e:
            print(f"DATABASE CONNECTION ERROR: {e}")
            print(f"MONGO_URL being used: {MONGO_URL[:30]}...")
            
    asyncio.create_task(init_db_indexes())

# Health check endpoint to verify DB connectivity
@app.get("/health")
async def health_check():
    try:
        await asyncio.wait_for(client.admin.command('ping'), timeout=5.0)
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}

# --- API ROUTES ---

@app.post("/api/auth/signup")
async def signup(user: UserSignup):
    try:
        # Check if user already exists (with 10s timeout)
        existing_user = await asyncio.wait_for(
            db["users"].find_one({"username": user.username}), timeout=10.0
        )
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already exists")
        
        hashed_password = hashlib.sha256(user.password.encode()).hexdigest()
        await asyncio.wait_for(
            db["users"].insert_one({
                "username": user.username,
                "password": hashed_password
            }), timeout=10.0
        )
        return {"message": "Signup successful!"}
    except asyncio.TimeoutError:
        print("SIGNUP TIMEOUT: MongoDB query took too long!")
        raise HTTPException(status_code=503, detail="Database is not responding. Please try again in a moment.")
    except HTTPException:
        raise
    except Exception as e:
        print(f"SIGNUP ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.post("/api/auth/login")
async def login(username: str = Form(...), password: str = Form(...)):
    try:
        # Query with 10s timeout to prevent infinite hang
        user = await asyncio.wait_for(
            db["users"].find_one({"username": username}), timeout=10.0
        )
        if not user:
            raise HTTPException(status_code=400, detail="Invalid username or password")
        
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        if user["password"] != hashed_password:
            raise HTTPException(status_code=400, detail="Invalid username or password")
        
        # Generate a dummy token or a simple token
        token = f"dummy-token-{username}"
        return {"access_token": token, "token_type": "bearer"}
    except asyncio.TimeoutError:
        print("LOGIN TIMEOUT: MongoDB query took too long!")
        raise HTTPException(status_code=503, detail="Database is not responding. Please try again in a moment.")
    except HTTPException:
        raise
    except Exception as e:
        print(f"LOGIN ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# 1. Post a Room with Multi-File Upload (Images/Videos)
@app.post("/api/rooms", response_model=dict)
async def create_room(
    landlord_name: str = Form(...),
    phone: str = Form(...),
    city: str = Form(...),
    rent: int = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    description: str = Form(...),
    amenities: str = Form(None),
    files: List[UploadFile] = File(...)
):
    counter = await db["counters"].find_one({"_id": "room_counter"})
    current_count = counter["count"] if counter else 0
    is_free = current_count < 2000

    saved_media_urls = []
    for file in files:
        unique_filename = f"{int(time.time())}_{file.filename.replace(' ', '_')}"
        file_location = os.path.join(UPLOAD_DIR, unique_filename)
        
        with open(file_location, "wb+") as file_object:
            file_object.write(file.file.read())
        
        saved_media_urls.append(f"/uploads/{unique_filename}")

    amenities_list = [a.strip() for a in amenities.split(",")] if amenities else []

    room_document = {
        "landlord_name": landlord_name,
        "phone": phone,
        "city": city,
        "rent": rent,
        "location": {
            "type": "Point",
            "coordinates": [longitude, latitude] # GeoJSON standard uses [longitude, latitude] order
        },
        "available": True,
        "description": description,
        "amenities": amenities_list,
        "media": saved_media_urls,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "listing_number": current_count + 1,
        "is_free": is_free
    }

    result = await db["rooms"].insert_one(room_document)
    await db["counters"].update_one({"_id": "room_counter"}, {"$inc": {"count": 1}})

    return {"status": "success", "message": "Room listed successfully!", "room_id": str(result.inserted_id)}

# 2. Get Platform Stats
@app.get("/api/stats")
async def get_stats():
    counter = await db["counters"].find_one({"_id": "room_counter"})
    total_listings = counter["count"] if counter else 0
    remaining_free = max(0, 2000 - total_listings)
    return {
        "total_listings": total_listings,
        "remaining_free_slots": remaining_free,
        "is_premium_active": total_listings >= 2000
    }

# 3. Hyperlocal Search Route ($nearSphere)
@app.get("/api/rooms/nearby")
async def get_nearby_rooms(
    lat: float = Query(..., description="User's Current Latitude"),
    lng: float = Query(..., description="User's Current Longitude"),
    radius_km: float = Query(5.0, description="Search radius in kilometers"),
    max_rent: Optional[int] = Query(None, description="Filter by Maximum Rent"),
    amenities: Optional[str] = Query(None, description="Amenities filter")
):
    radius_in_meters = radius_km * 1000

    query = {
        "available": True,
        "location": {
            "$nearSphere": {
                "$geometry": {
                    "type": "Point",
                    "coordinates": [lng, lat]
                },
                "$maxDistance": radius_in_meters
            }
        }
    }

    if max_rent:
        query["rent"] = {"$lte": max_rent}

    if amenities:
        required_amenities = [a.strip() for a in amenities.split(",")]
        query["amenities"] = {"$all": required_amenities}

    cursor = db["rooms"].find(query)
    rooms = []
    
    async for doc in cursor:
        rooms.append({
            "id": str(doc["_id"]),
            "city": doc["city"],
            "rent": doc["rent"],
            "latitude": doc["location"]["coordinates"][1],
            "longitude": doc["location"]["coordinates"][0],
            "description": doc["description"],
            "amenities": doc["amenities"],
            "media": doc["media"],
            "listing_number": doc["listing_number"],
            "is_free": doc["is_free"]
        })
        
    return rooms

# 4. Scratch Card Reveal Endpoint
@app.get("/api/rooms/{room_id}/reveal")
async def reveal_landlord_contact(room_id: str):
    if not ObjectId.is_valid(room_id):
        raise HTTPException(status_code=400, detail="Invalid Room ID format")
        
    room = await db["rooms"].find_one({"_id": ObjectId(room_id), "available": True})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
        
    return {
        "landlord_name": room["landlord_name"],
        "phone": room["phone"],
        "message": "Contact unlocked successfully!"
    }

# 5. Unlist / Delete Property
@app.delete("/api/rooms/{room_id}")
async def unlist_room(room_id: str):
    if not ObjectId.is_valid(room_id):
        raise HTTPException(status_code=400, detail="Invalid Room ID")
        
    result = await db["rooms"].update_one(
        {"_id": ObjectId(room_id)},
        {"$set": {"available": False}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Room not found")
        
    return {"status": "success", "message": "Room successfully unlisted"}