# get_reviews.py

import requests
from utils.place_info import load_google_api_key

GOOGLE_PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

def get_reviews_for_place(place_id, max_reviews=10, min_words=3):
    """
    Fetches up to `max_reviews` user reviews for a place.
    Cleans out short/low-quality reviews.
    Returns a list of review texts.
    """
    api_key = load_google_api_key()

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

        return reviews

    except requests.exceptions.RequestException as e:
        print(f"🌐 Network error fetching reviews for {place_id}: {e}")
        return []

    except Exception as e:
        print(f"❌ Unexpected error while fetching reviews for {place_id}: {e}")
        return []
