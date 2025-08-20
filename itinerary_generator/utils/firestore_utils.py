import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import math

# Initialize Firestore (only if not already initialized)
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)

db = firestore.client()


def fetch_pois_from_firestore(location: str, query: str = "", cursor=None, limit: int = 15):
    """
    Fetch POIs from Firestore for a given location and optional search query.
    Uses cursor-based pagination.
    """
    collection_ref = db.collection("places").document(location).collection("poi_list")

    query_ref = collection_ref.order_by("score", direction=firestore.Query.DESCENDING)

    if query:
        # naive substring match on name, tags, types
        query_ref = query_ref.where("name", ">=", query).where("name", "<=", query + "\uf8ff")

    if cursor:
        query_ref = query_ref.start_after(cursor)

    docs = query_ref.limit(limit).stream()

    pois = []
    last_doc = None

    for doc in docs:
        pois.append(doc.to_dict())
        last_doc = doc

    return pois, last_doc


def cache_poi_to_firestore(location: str, poi_data: dict):
    """
    Cache a new POI into Firestore.
    If it already exists, update metadata (rating, review_count, etc).
    """
    place_id = poi_data["place_id"]
    doc_ref = db.collection("places").document(location).collection("poi_list").document(place_id)

    poi_data["updated_at"] = datetime.utcnow().isoformat()

    # merge=True → only update fields, don’t overwrite whole doc
    doc_ref.set(poi_data, merge=True)


def increment_visit_count(location: str, place_id: str):
    """
    Safely increment visit_count for a POI.
    Uses Firestore atomic increment.
    """
    doc_ref = d_
