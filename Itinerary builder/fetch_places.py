# fetch_places.py

import requests
import time
import json
import os
from utils.place_info import load_google_api_key, map_price_level

GOOGLE_PLACES_API_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
GEOCODE_API_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# 🔹 Optional: In-memory cache for coordinates to avoid repeat Geocode API calls
_location_cache = {}

# 🔹 Basic file-based cache for place search results
_CACHE_FILE = os.path.join("cache", "places_cache.json")


def _load_cache():
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
    with open(_CACHE_FILE, "w") as f:
        json.dump(cache, f)


_places_cache = _load_cache()

def get_coordinates_for_location(location, api_key):
    """Fetch dynamic lat/lng for a location using Google Geocoding API (with caching)."""
    if location in _location_cache:
        return _location_cache[location]

    params = {"address": location, "key": api_key}
    res = requests.get(GEOCODE_API_URL, params=params).json()

    if res["status"] == "OK":
        loc = res["results"][0]["geometry"]["location"]
        coords = {"lat": loc["lat"], "lng": loc["lng"]}
        _location_cache[location] = coords
        return coords
    else:
        raise ValueError(f"Could not fetch coordinates for {location}. API status: {res['status']}")

def construct_photo_url(photo_reference, api_key):
    """Build a photo URL from Google Places photo_reference."""
    if not photo_reference:
        return None
    return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference={photo_reference}&key={api_key}"

def fetch_places(location, max_results=100, radius=15000, use_cache=True):
    """Fetch top tourist attractions for a location and map budget levels with disclaimers.
    Results are cached based on request parameters to avoid redundant API calls.
    """
    api_key = load_google_api_key()

    cache_key = f"{location}-{max_results}-{radius}"
    if use_cache and cache_key in _places_cache:
        return _places_cache[cache_key]

    # ✅ Dynamically get coordinates with caching
    coords = get_coordinates_for_location(location, api_key)
    lat_lng = f"{coords['lat']},{coords['lng']}"

    params = {
        "location": lat_lng,
        "radius": radius,
        "keyword": "tourist attractions",
        "key": api_key
    }

    results = []
    seen_place_ids = set()

    while len(results) < max_results:
        response = requests.get(GOOGLE_PLACES_API_URL, params=params)
        data = response.json()

        if "results" not in data:
            break

        for place in data["results"]:
            if place["place_id"] in seen_place_ids:
                continue

            photo_reference = None
            if "photos" in place:
                photo_reference = place["photos"][0].get("photo_reference")

            # ✅ Map price level to a budget string
            budget = map_price_level(place.get("price_level"))
            disclaimer = "Price info not available" if budget == "unknown" else ""

            place_data = {
                "place_id": place["place_id"],
                "name": place["name"],
                "rating": place.get("rating"),
                "user_ratings_total": place.get("user_ratings_total"),
                "price_level": place.get("price_level"),
                "budget_category": budget,
                "types": place.get("types", []),
                "coordinates": place["geometry"]["location"],
                "photo_url": construct_photo_url(photo_reference, api_key),
                "disclaimer": disclaimer
            }

            results.append(place_data)
            seen_place_ids.add(place["place_id"])

        # ✅ Handle pagination
        if "next_page_token" in data:
            time.sleep(2)  # Google requires a delay before using next_page_token
            params = {"key": api_key, "pagetoken": data["next_page_token"]}
        else:
            break

    trimmed = results[:max_results]
    if use_cache:
        _places_cache[cache_key] = trimmed
        _save_cache(_places_cache)
    return trimmed
