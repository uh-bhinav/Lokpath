# get_reviews.py

import requests
import json
import os
from .utils.place_info import load_google_api_key

GOOGLE_PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# 🔹 Basic file-based cache for place reviews
_CACHE_FILE = os.path.join("cache", "reviews_cache.json")


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


_reviews_cache = _load_cache()

def get_reviews_for_place(place_id, max_reviews=10, min_words=3, use_cache=True):
    """
    Fetches up to `max_reviews` user reviews for a place.
    Cleans out short/low-quality reviews.
    Results are cached to avoid repeat API calls.
    Returns a list of review texts.
    """
    api_key = load_google_api_key()

    cache_key = f"{place_id}-{max_reviews}-{min_words}"
    if use_cache and cache_key in _reviews_cache:
        return _reviews_cache[cache_key]

    params = {
        "place_id": place_id,
        "fields": "review",
        "key": api_key
    }

    try:
        response = requests.get(GOOGLE_PLACE_DETAILS_URL, params=params)
        data = response.json()

        # ✅ Handle API error states
        status = data.get("status")
        if status and status != "OK":
            print(f"⚠️ Google API returned status {status} for place_id {place_id}")
            return []

        # ✅ Safely handle missing reviews
        reviews_data = data.get("result", {}).get("reviews", [])
        if not reviews_data:
            return []

        # ✅ Clean and filter reviews
        reviews = []
        for r in reviews_data[:max_reviews]:
            text = r.get("text", "").strip()
            if len(text.split()) >= min_words:  # Filter out "Good", "Nice", etc.
                reviews.append(text)

        if use_cache:
            _reviews_cache[cache_key] = reviews
            _save_cache(_reviews_cache)

        return reviews

    except requests.exceptions.RequestException as e:
        print(f"🌐 Network error fetching reviews for {place_id}: {e}")
        return []

    except Exception as e:
        print(f"❌ Unexpected error while fetching reviews for {place_id}: {e}")
        return []
