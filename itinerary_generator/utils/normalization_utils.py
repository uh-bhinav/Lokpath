# Lokpath/itinerary_generator/utils/normalization_utils.py

from typing import Dict, Any, Optional

def normalize_google_place(place: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a Google Places API response into a consistent POI format.
    """
    return {
        "poi_id": place.get("place_id"),
        "name": place.get("name"),
        "location": {
            "lat": place.get("geometry", {}).get("location", {}).get("lat"),
            "lng": place.get("geometry", {}).get("location", {}).get("lng"),
        },
        "address": place.get("formatted_address") or place.get("vicinity"),
        "rating": place.get("rating", 0.0),
        "types": place.get("types", []),
        "photo_reference": _extract_photo_reference(place),
        "source": "google_places",
        "tags": [],  # to be filled later by tagging_utils
    }


def normalize_firestore_place(place_id: str, place_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a Firestore POI entry into the same POI format.
    """
    return {
        "poi_id": place_id,
        "name": place_data.get("name"),
        "location": {
            "lat": place_data.get("location", {}).get("lat"),
            "lng": place_data.get("location", {}).get("lng"),
        },
        "address": place_data.get("address"),
        "rating": place_data.get("rating", 0.0),
        "types": place_data.get("types", []),
        "photo_reference": place_data.get("photo_reference"),
        "source": "firestore",
        "tags": place_data.get("tags", []),
    }


def _extract_photo_reference(place: Dict[str, Any]) -> Optional[str]:
    """
    Extracts the photo reference from a Google Places API response, if available.
    """
    photos = place.get("photos")
    if photos and isinstance(photos, list) and "photo_reference" in photos[0]:
        return photos[0]["photo_reference"]
    return None
