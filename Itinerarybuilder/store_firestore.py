# store_firestore.py

import firebase_admin
from firebase_admin import credentials, firestore
from .utils.firebase_utils import get_service_account_path
import datetime
from google.api_core.exceptions import GoogleAPIError

# ✅ Initialize Firestore only once
if not firebase_admin._apps:
    cred = credentials.Certificate(get_service_account_path())
    firebase_admin.initialize_app(cred)

db = firestore.client()

def store_itinerary(user_id, location, start_date, end_date, itinerary, trip_id):
    """
    Stores a complete itinerary under:
    diary/{user_id}/itineraries/{trip_id}
    Includes timestamp, metadata, and nested day-wise POIs.
    """
    try:
        
        doc_ref = db.collection('users').document(user_id).collection('itineraries').document(trip_id)

        # ✅ Data structure for scalable storage
        data = {
            "trip_id": trip_id,
            "user_id": user_id,
            "location": location,
            "start_date": start_date,
            "end_date": end_date,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "itinerary": itinerary,  # Nested dict with Day 1/Day 2 and POI objects
            "poi_count": sum(len(day) for day in itinerary.values())  # Useful for analytics
        }

        doc_ref.set(data)
        print(f"\n✅ Itinerary stored successfully for user: {user_id}, trip_id: {trip_id}")

    except GoogleAPIError as e:
        print(f"❌ Firestore API Error while storing itinerary for {user_id}: {e}")
    except Exception as e:
        print(f"❌ Unexpected error while storing itinerary for {user_id}: {e}")
