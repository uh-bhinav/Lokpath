# Lokpath/itinerary_generator/utils/suggestion_utils.py

from firebase_admin import firestore
from .google_places_utils import fetch_google_places
from .normalization_utils import normalize_text

db = firestore.client()

def get_default_suggestions(location: str, limit: int = 10):
    """
    Fetches default POI suggestions before user types anything.
    - First tries Firestore (cached POIs).
    - If none exist, falls back to Google Places API.
    """
    suggestions = []

    # 1. Try Firestore POIs
    firestore_ref = db.collection("places").document(location).collection("poi_list")
    docs = firestore_ref.limit(limit).stream()

    for doc in docs:
        data = doc.to_dict()
        suggestions.append({
            "name": data.get("name"),
            "id": doc.id,
            "source": "firestore"
        })

    # 2. Fallback to Google Places if no Firestore data
    if not suggestions:
        google_pois = fetch_google_places(location, "tourist attractions")
        for poi in google_pois[:limit]:
            suggestions.append({
                "name": poi.get("name"),
                "id": poi.get("place_id"),
                "source": "google_places"
            })

    return suggestions


def filter_suggestions(location: str, query: str, limit: int = 10):
    """
    Filters POIs in Firestore and Google Places based on user input.
    Case-insensitive, accent-insensitive search.
    """
    normalized_query = normalize_text(query)
    suggestions = []

    # 1. Firestore Search
    firestore_ref = db.collection("places").document(location).collection("poi_list")
    docs = firestore_ref.stream()

    for doc in docs:
        data = doc.to_dict()
        poi_name = normalize_text(data.get("name", ""))
        if normalized_query in poi_name:
            suggestions.append({
                "name": data.get("name"),
                "id": doc.id,
                "source": "firestore"
            })

    # 2. Fallback to Google Places if suggestions are still few
    if len(suggestions) < limit:
        google_pois = fetch_google_places(location, "tourist attractions")
        for poi in google_pois:
            poi_name = normalize_text(poi.get("name", ""))
            if normalized_query in poi_name:
                # Avoid duplicates (same name in Firestore & Google Places)
                if poi.get("name") not in [s["name"] for s in suggestions]:
                    suggestions.append({
                        "name": poi.get("name"),
                        "id": poi.get("place_id"),
                        "source": "google_places"
                    })

    return suggestions[:limit]
