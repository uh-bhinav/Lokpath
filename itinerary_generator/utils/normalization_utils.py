# Lokpath/itinerary_generator/utils/normalization_utils.py

from typing import Dict, Any, Optional
import unicodedata

# Note: Keep only helpers that do not duplicate Itinerarybuilder utils.
# We intentionally avoid duplicating fetch/price mapping/etc.


def normalize_text(value: str) -> str:
    """Normalize text for case-insensitive and accent-insensitive matching.
    - Lowercases
    - Strips/condenses whitespace
    - Removes diacritics (accents)
    """
    if not isinstance(value, str):
        return ""
    # Remove accents
    no_accents = unicodedata.normalize("NFKD", value)
    no_accents = "".join(ch for ch in no_accents if not unicodedata.combining(ch))
    # Lower and collapse whitespace
    lowered = no_accents.lower()
    return " ".join(lowered.split())


def _extract_photo_reference(place: Dict[str, Any]) -> Optional[str]:
    """Extracts the photo reference from a Google Places API response, if available."""
    photos = place.get("photos") if isinstance(place, dict) else None
    if photos and isinstance(photos, list) and photos and isinstance(photos[0], dict):
        return photos[0].get("photo_reference")
    return None


def normalize_google_place(place: Dict[str, Any]) -> Dict[str, Any]:
    """Lightweight normalization for Google Places payload if needed by callers.
    This does not duplicate any Itinerarybuilder transformation logic.
    """
    return {
        "poi_id": place.get("place_id"),
        "name": place.get("name"),
        "address": place.get("formatted_address") or place.get("vicinity", ""),
        "rating": place.get("rating", 0.0),
        "types": place.get("types", []),
        "photo_reference": _extract_photo_reference(place),
        "source": "google_places",
        "tags": [],
    }


def normalize_firestore_place(place_id: str, place_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a Firestore POI entry into a simple POI format for suggestions."""
    return {
        "poi_id": place_id,
        "name": place_data.get("name", ""),
        "address": place_data.get("address", ""),
        "rating": place_data.get("rating", 0.0),
        "types": place_data.get("types", []),
        "photo_reference": place_data.get("photo_reference"),
        "source": "firestore",
        "tags": place_data.get("tags", []),
    }
