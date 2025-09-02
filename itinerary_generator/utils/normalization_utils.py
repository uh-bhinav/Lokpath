# itinerary_generator/utils/normalization_utils.py
"""
Normalization utilities to align external POI data (Google Places, etc.)
into the canonical Firestore schema under:
  /places/{location}/poi_list/{place_id}
"""
import os

from typing import Dict, Any, List
from datetime import datetime


def normalize_place(place: Dict[str, Any], location: str) -> Dict[str, Any]:
    """
    Normalize a raw Google Places result into Firestore's schema.
    """
    return {
        "place_id": place.get("place_id", ""),
        "name": place.get("name", ""),
        "coordinates": {
            "lat": place.get("geometry", {}).get("location", {}).get("lat", 0.0),
            "lng": place.get("geometry", {}).get("location", {}).get("lng", 0.0),
        },
        "rating": place.get("rating"),
        "user_ratings_total": place.get("user_ratings_total", 0),
        "price_level": place.get("price_level"),  # may be null
        "budget_category": place.get("budget_category", "unknown"),
        "photo_url": _extract_photo_url(place),
        "tags": _derive_tags(place),
        "types": place.get("types", []),
        "kid_friendly": place.get("kid_friendly", False),
        "pet_friendly": place.get("pet_friendly", False),
        "wheelchair_accessible": place.get("wheelchair_accessible", False),
        "disclaimer": place.get("disclaimer", ""),
        "source": "google_places",
        "visit_count": place.get("visit_count", 0),   # ensure consistency
        "created_at": datetime.utcnow().isoformat(),
    }


def _extract_photo_url(place: Dict[str, Any]) -> str:
    """
    Extract a usable photo URL if present.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "YOUR_API_KEY")
    photos = place.get("photos", [])
    if photos:
        ref = photos[0].get("photo_reference")
        if ref:
            return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference={ref}&key={api_key}"
    return place.get("photo_url", "")  # fallback if already enriched


def _derive_tags(place: Dict[str, Any]) -> List[str]:
    """
    Derive human-friendly tags from the raw data.
    """
    tags: List[str] = []
    types = place.get("types", [])
    name = (place.get("name") or "").lower()

    if "park" in types or "natural_feature" in types or "tourist_attraction" in types:
        tags.append("nature")
    if "waterfall" in name:
        tags.extend(["photogenic", "adventurous"])
    if place.get("rating", 0) >= 4.5:
        tags.append("romantic")
    if place.get("kid_friendly"):
        tags.append("family-friendly")
    if "temple" in types or "garden" in types:
        tags.append("peaceful")

    # Extend with pre-assigned tags and deduplicate
    tags.extend(place.get("tags", []))
    return sorted(set(tags))

def normalize_text(text: str) -> str:
    """
    Normalizes text for searching by converting to lowercase and stripping whitespace.
    Handles non-string inputs gracefully.
    """
    if not isinstance(text, str):
        return ""
    return text.lower().strip()