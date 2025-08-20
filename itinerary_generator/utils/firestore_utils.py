import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# Initialize Firestore (only once)
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)

db = firestore.client()


def fetch_pois_from_firestore(location: str, query: str = "", cursor=None, limit: int = 15, is_hidden_gem: bool = False):
    """
    Fetch POIs from Firestore for a given location and optional search query.
    Uses cursor-based pagination.
    Supports both public places and hidden gems.
    """
    collection_root = "hidden_gems" if is_hidden_gem else "places"
    collection_ref = db.collection(collection_root).document(location).collection("poi_list")

    query_ref = collection_ref.order_by("rating", direction=firestore.Query.DESCENDING)

    if query:
        # Prefix match on name (Firestore limitation)
        query_ref = query_ref.where("name", ">=", query).where("name", "<=", query + "\uf8ff")

    if cursor:
        # cursor must be a DocumentSnapshot, not a dict
        query_ref = query_ref.start_after(cursor)

    docs = query_ref.limit(limit).stream()

    pois = []
    last_doc = None

    for doc in docs:
        poi_data = doc.to_dict()
        poi_data["place_id"] = doc.id  # ensure place_id is included
        pois.append(poi_data)
        last_doc = doc

    return pois, last_doc


def cache_poi_to_firestore(location: str, poi_data: dict, is_hidden_gem: bool = False):
    """
    Cache a new POI into Firestore.
    If it already exists, update metadata (rating, review_count, etc).
    Works for both hidden_gems and public places.
    """
    place_id = poi_data["place_id"]
    collection_root = "hidden_gems" if is_hidden_gem else "places"
    doc_ref = db.collection(collection_root).document(location).collection("poi_list").document(place_id)

    # Ensure essential defaults exist
    poi_data.setdefault("visit_count", 0)
    poi_data["updated_at"] = datetime.utcnow().isoformat()

    doc_ref.set(poi_data, merge=True)


def increment_visit_count(location: str, place_id: str, is_hidden_gem: bool = False):
    """
    Safely increment visit_count for a POI.
    Uses Firestore atomic increment.
    """
    try:
        collection_root = "hidden_gems" if is_hidden_gem else "places"
        doc_ref = db.collection(collection_root).document(location).collection("poi_list").document(place_id)

        doc_ref.update({
            "visit_count": firestore.Increment(1)
        })

        print(f"✅ visit_count incremented for {collection_root}/{location}/poi_list/{place_id}")

    except Exception as e:
        print(f"❌ Error incrementing visit_count: {e}")
