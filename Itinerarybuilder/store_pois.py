# store_pois.py

import firebase_admin
from firebase_admin import credentials, firestore
from .utils.firebase_utils import get_service_account_path
from google.api_core.exceptions import GoogleAPIError
import datetime

# ✅ Initialize Firestore only once
if not firebase_admin._apps:
    cred = credentials.Certificate(get_service_account_path())
    firebase_admin.initialize_app(cred)

db = firestore.client()

def store_pois(location, pois, batch_size=300):
    """
    Stores POIs under 'places/{location}/poi_list'.
    ✅ Adds metadata (created_at, source).
    ✅ Handles duplicates gracefully.
    ✅ Uses batch commits for scalability.
    ✅ Fully compatible with run_pipeline, query_firestore, itinerary_builder.
    """
    # Normalize the location so collections are consistent
    location = location.lower()

    poi_ref = db.collection("places").document(location).collection("poi_list")
    saved_count = 0
    skipped_count = 0

    try:
        batch = db.batch()
        ops_in_batch = 0

        for poi in pois:
            place_id = poi.get("place_id")
            if not place_id:
                skipped_count += 1
                print(f"⚠️ Skipping POI with no place_id: {poi.get('name')}")
                continue

            # ✅ Normalize required fields for consistency across pipeline
            poi.setdefault("budget_category", "unknown")
            poi.setdefault("disclaimer", "")
            poi.setdefault("tags", [])
            poi.setdefault("types", [])
            poi.setdefault("photo_url", "")
            poi.setdefault("coordinates", {})
            poi.setdefault("kid_friendly", None)
            poi.setdefault("pet_friendly", None)
            poi.setdefault("wheelchair_accessible", None)

            # ✅ Add metadata
            poi["created_at"] = datetime.datetime.utcnow().isoformat()
            poi.setdefault("source", "google_places")

            doc_ref = poi_ref.document(place_id)

            # ✅ Skip duplicates unless data has changed
            existing_doc = doc_ref.get()
            if existing_doc.exists:
                existing_data = existing_doc.to_dict()
                if existing_data == poi:
                    skipped_count += 1
                    continue

            batch.set(doc_ref, poi)
            saved_count += 1
            ops_in_batch += 1

            # ✅ Commit batch every `batch_size` to avoid Firestore 500 writes limit
            if ops_in_batch >= batch_size:
                batch.commit()
                batch = db.batch()
                ops_in_batch = 0

        # ✅ Commit any remaining writes
        if ops_in_batch > 0:
            batch.commit()

        print(f"✅ Stored {saved_count} new POIs under 'places/{location}/poi_list' ({skipped_count} skipped/duplicates)")

    except GoogleAPIError as e:
        print(f"❌ Firestore API Error while storing POIs for {location}: {e}")
    except Exception as e:
        print(f"❌ Unexpected error while storing POIs for {location}: {e}")
