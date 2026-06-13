import asyncio
import os
import sys
import time
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Path set kar rahe hain taaki python .env file ko dhoondh sake
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

MONGO_URL = os.getenv("MONGO_URL")

if not MONGO_URL:
    print("Error: .env file me MONGO_URL nahi mila! Pehle check karo.")
    sys.exit(1)

# Dummy Rooms Data centered around Nagpur coordinates
dummy_rooms = [
    {
        "landlord_name": "Ramesh Sharma",
        "phone": "9876543210",
        "city": "Nagpur",
        "rent": 4500,
        "location": {"type": "Point", "coordinates": [79.0682, 21.1458]}, # Dharampeth Area
        "available": True,
        "description": "Beautiful single room near Dharampeth market. Best for students. 24/7 water supply.",
        "amenities": ["WiFi", "Parking"],
        "media": ["https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af"], # High quality dummy image
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "listing_number": 1,
        "is_free": True
    },
    {
        "landlord_name": "Sunita Rao",
        "phone": "9123456789",
        "city": "Nagpur",
        "rent": 7500,
        "location": {"type": "Point", "coordinates": [79.0882, 21.1558]}, # Sadar Area
        "available": True,
        "description": "1 BHK Flat in Sadar. Fully furnished with AC and modular kitchen. Ready to move.",
        "amenities": ["WiFi", "AC", "Parking", "Geyser"],
        "media": ["https://images.unsplash.com/photo-1502672260266-1c1ef2d93688"],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "listing_number": 2,
        "is_free": True
    },
    {
        "landlord_name": "Amit Deshmukh",
        "phone": "8888888888",
        "city": "Nagpur",
        "rent": 3500,
        "location": {"type": "Point", "coordinates": [79.0582, 21.1258]}, # Pratap Nagar
        "available": True,
        "description": "Cozy RK room near IT Park. Perfect for working professionals. No restrictions.",
        "amenities": ["WiFi"],
        "media": ["https://images.unsplash.com/photo-1598928506311-c55ded91a20c"],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "listing_number": 3,
        "is_free": True
    },
    {
        "landlord_name": "Vikram Singh",
        "phone": "7777777777",
        "city": "Nagpur",
        "rent": 5000,
        "location": {"type": "Point", "coordinates": [79.0782, 21.1358]}, # Sitabuldi
        "available": True,
        "description": "Room on 2nd floor near Metro Station Sitabuldi. Easy connectivity everywhere.",
        "amenities": ["Parking", "Guard"],
        "media": ["https://images.unsplash.com/photo-1536376072261-38c75010e6c9"],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "listing_number": 4,
        "is_free": True
    }
]

async def seed_database():
    print("Connecting to MongoDB Atlas...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client["roomfinder_db"]
    
    # Purana koi data ho toh saaf kar dete hain fresh start ke liye
    print("Cleaning old records...")
    await db["rooms"].delete_many({})
    await db["counters"].delete_many({})
    
    # Set counter to 4 because we are inserting 4 rooms
    await db["counters"].insert_one({"_id": "room_counter", "count": 4})
    
    print(f"Inserting {len(dummy_rooms)} Nagpur room listings into cloud...")
    result = await db["rooms"].insert_many(dummy_rooms)
    
    print("Creating Geospatial 2dsphere Index...")
    await db["rooms"].create_index([("location", "2dsphere")])
    
    print("\n🎉 SUCCESS! Database successfully seeded with Nagpur rooms data!")
    client.close()

if __name__ == "__main__":
    asyncio.run(seed_database())