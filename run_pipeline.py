# run_pipeline.py
import os
from dotenv import load_dotenv
load_dotenv()
import firebase_admin
from firebase_admin import credentials, firestore

FIREBASE_SERVICE_ACCOUNT_CONTENT = os.environ.get('FIREBASE_SERVICE_ACCOUNT_CONTENT')
FIREBASE_SERVICE_ACCOUNT_PATH = "credentials/lokpath-2d9a0-firebase-adminsdk-fbsvc-cd5812102d.json"

def _initialize_firebase_for_script():
    # This function should only be called once, so _apps check is important
    if not firebase_admin._apps: 
        if FIREBASE_SERVICE_ACCOUNT_CONTENT:
            import json
            cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_CONTENT))
            firebase_admin.initialize_app(cred)
            print("Firebase initialized for script using environment variable.")
        elif os.path.exists(FIREBASE_SERVICE_ACCOUNT_PATH):
            cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
            firebase_admin.initialize_app(cred)
            print("Firebase initialized for script using local file.")
        else:
            raise FileNotFoundError(
                f"Firebase service account not found for script. Expected env var FIREBASE_SERVICE_ACCOUNT_CONTENT "
                f"or file at {FIREBASE_SERVICE_ACCOUNT_PATH}."
            )
        
_initialize_firebase_for_script()

from query_firestore import get_filtered_pois
from fetch_places import fetch_places
from get_reviews import get_reviews_for_place
from tag_reviews import tag_place_with_reviews
from itinerary_builder import generate_itinerary
from store_firestore import store_itinerary
from store_pois import store_pois
from utils.itinerary_utils import estimate_required_pois
from utils.place_info import map_price_level
import uuid
        
# 🧪 Simulated user input (replace with frontend values in production)
user_input = {
    "user_id": "user_123",
    "location": "bengaluru",
    "start_date": "2025-05-01",
    "end_date": "2025-05-02",
    "selected_interests": ["sunset", "romantic", "peaceful", "trek"],
    "budget": "low",
    "with_kids": True,
    "with_pets": False,
    "with_disabilities": False
}

# ✅ Step 1: Estimate POIs required based on trip length
required_pois = estimate_required_pois(user_input["start_date"], user_input["end_date"])

# ✅ Step 2: Query Firestore for existing POIs
filtered_pois = get_filtered_pois(user_input)

# ✅ Step 3: Fallback to Google Places if insufficient POIs
if len(filtered_pois) < required_pois:
    print(f"⚠️ Only {len(filtered_pois)} POIs found, but {required_pois} needed.")
    print("📥 Fetching additional POIs from Google Places...")

    new_places = fetch_places(user_input["location"])

    for place in new_places:
        reviews = get_reviews_for_place(place["place_id"])
        tags = tag_place_with_reviews(place["name"], reviews)

        # ✅ Normalize for Firestore schema
        place["tags"] = tags
        place["budget_category"] = map_price_level(place.get("price_level"))
        place.setdefault("kid_friendly", False)
        place.setdefault("pet_friendly", False)
        place.setdefault("wheelchair_accessible", False)
        place.setdefault("disclaimer", "")

    # ✅ Save new POIs to Firestore
    store_pois(user_input["location"], new_places)

    # ✅ Re-query to include newly saved POIs
    filtered_pois = get_filtered_pois(user_input)

# ✅ Step 4: Generate itinerary (multi-day plan)
itinerary = generate_itinerary(
    filtered_pois,
    user_input["start_date"],
    user_input["end_date"],
    enable_hidden_gems=True
)

# ✅ Step 5: Generate unique trip ID
trip_id = str(uuid.uuid4())

# ✅ Step 6: Store final itinerary in diary collection
store_itinerary(
    user_input["user_id"],
    user_input["location"],
    user_input["start_date"],
    user_input["end_date"],
    itinerary,
    trip_id
)

# ✅ Step 7: Print summary
print("\n📌 Itinerary Generated:")
for day, activities in itinerary.items():
    print(f"\n📅 {day}")
    if not activities:
        print("  (Rest Day)")
    else:
        for a in activities:
            print(f"  → {a['time_slot']} | {a['name']} | {a['tags']} {a.get('disclaimer', '')}")
