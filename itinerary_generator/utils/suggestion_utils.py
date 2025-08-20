# Lokpath/itinerary_generator/utils/suggestion_utils.py
"""Suggestion helpers used by the /search-places route.
- No direct Firebase initialization here; the route passes a db client.
- Google Places access is delegated to Itinerarybuilder via wrapper.
"""
from typing import List, Dict, Any
from .google_places_utils import fetch_google_places
from .normalization_utils import normalize_text


def get_default_suggestions(db, location: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Default POI suggestions before user types anything.
    1) Try Firestore cached POIs
    2) Fallback to Google Places
    """
    suggestions: List[Dict[str, Any]] = []

    # 1. Try Firestore POIs
    firestore_ref = db.collection("places").document(location.lower()).collection("poi_list")
    docs = firestore_ref.limit(limit).stream()

    for doc in docs:
        data = doc.to_dict() or {}
        suggestions.append({
            "name": data.get("name", ""),
            "address": data.get("address", ""),
            "tags": data.get("tags", []),
            "source": "firestore",
        })

    # 2. Fallback to Google Places if no Firestore data
    if not suggestions:
        google_pois = fetch_google_places(location, max_results=limit * 2)
        for poi in google_pois[:limit]:
            suggestions.append({
                "name": poi.get("name", ""),
                "address": poi.get("vicinity") or poi.get("formatted_address", ""),
                "tags": poi.get("tags", []),
                "source": "google_places",
            })

    return suggestions


def filter_suggestions(db, location: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Filter POIs for suggestion-as-you-type.
    Accent-insensitive, case-insensitive substring match.
    """
    normalized_query = normalize_text(query)
    suggestions: List[Dict[str, Any]] = []

    # 1. Firestore Search (client-side substring match)
    firestore_ref = db.collection("places").document(location.lower()).collection("poi_list")
    docs = firestore_ref.stream()

    for doc in docs:
        data = doc.to_dict() or {}
        poi_name = normalize_text(data.get("name", ""))
        if normalized_query in poi_name:
            suggestions.append({
                "name": data.get("name", ""),
                "address": data.get("address", ""),
                "tags": data.get("tags", []),
                "source": "firestore",
            })
            if len(suggestions) >= limit:
                return suggestions[:limit]

    # 2. Fallback to Google Places if still few
    if len(suggestions) < limit:
        google_pois = fetch_google_places(location, max_results=limit * 3)
        existing_names = {s["name"] for s in suggestions}
        for poi in google_pois:
            poi_name = poi.get("name", "")
            if normalize_text(poi_name).find(normalized_query) != -1 and poi_name not in existing_names:
                suggestions.append({
                    "name": poi_name,
                    "address": poi.get("vicinity") or poi.get("formatted_address", ""),
                    "tags": poi.get("tags", []),
                    "source": "google_places",
                })
                if len(suggestions) >= limit:
                    break

    return suggestions[:limit]
