
# tag_reviews.py
from tqdm import tqdm
import time
import requests
import os
import json

# Simple phrases indicating that a place may not welcome kids.  This is
# intentionally basic to avoid heavy NLP dependencies.
_KID_UNFRIENDLY_PHRASES = [
    "not kid friendly",
    "kids not allowed",
    "children not allowed",
    "no kids",
    "adults only",
    "not suitable for kids",
]


# 🔽 ADD THIS NEW HELPER FUNCTION 🔽
def infer_intensity_from_tags(tags):
    """Infers an intensity level from a list of POI tags."""
    high_intensity_tags = {"adventurous", "trek"}
    low_intensity_tags = {"relaxing", "peaceful", "quiet", "spiritual"}

    tag_set = set(tags)

    if not high_intensity_tags.isdisjoint(tag_set):
        return "high"
    if not low_intensity_tags.isdisjoint(tag_set):
        return "low"

    return "medium" # Default intensity

def has_kid_friendly_issues(reviews):
    """Return ``True`` if any review suggests kids may not be welcome."""
    for review in reviews or []:
        text = review.lower()
        for phrase in _KID_UNFRIENDLY_PHRASES:
            if phrase in text:
                return True
    return False

def tag_place_with_reviews(place_name, reviews):
    """
    Calls the dedicated Cloud Function to tag a place based on reviews.
    This keeps the main Flask app lightweight.
    """
    # Get the URL of your deployed Cloud Function from an environment variable
    function_url = os.environ.get('TAG_REVIEWS_FUNCTION_URL')

    if not function_url:
        print("ERROR: TAG_REVIEWS_FUNCTION_URL environment variable not set.")
        return {"tags": ["tagging_service_unavailable"], "intensity": "unknown"}

    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "place_name": place_name,
            "reviews": reviews
        }
        
        response = requests.post(function_url, data=json.dumps(payload), headers=headers, timeout=20) # Longer timeout for AI
        response.raise_for_status()
        
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not call the tag_place_with_reviews Cloud Function: {e}")
        return {"tags": ["tagging_service_error"], "intensity": "unknown"}

#Cache tags in Firestore.

#Only re-run tagging if reviews changed.