# itinerary_generator/utils/google_places_utils.py
"""Deduplicated wrapper around Itinerarybuilder.fetch_places.
Avoids any direct env handling here; credentials are loaded by existing utils.
"""
from typing import List, Dict, Any

# Reuse the canonical implementation
from Itinerarybuilder.fetch_places import fetch_places as _fetch_places


def fetch_google_places(location: str, max_results: int = 20, radius: int = 15000) -> List[Dict[str, Any]]:
    """Fetch POIs using the project's canonical Google Places fetcher.
    This simply forwards to Itinerarybuilder.fetch_places.
    """
    return _fetch_places(location=location, max_results=max_results, radius=radius)
