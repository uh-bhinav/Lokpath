# query_firestore.py

import firebase_admin
from firebase_admin import credentials, firestore
from utils.firebase_utils import get_service_account_path

# ✅ Initialize Firestore once
if not firebase_admin._apps:
    cred = credentials.Certificate(get_service_account_path())
    firebase_admin.initialize_app(cred)

db = firestore.client()

def get_filtered_pois(user_input):
    """
    Fetch and filter POIs from Firestore for a given location.
    Applies budget, interest tags, and accessibility filters.
    ✅ Safe for scaling.
    ✅ Works with both Google POIs and hidden gems.
    """
    # Normalize location so Firestore collections match `store_pois`
    location = user_input["location"].lower()
    user_tags = set(user_input.get("selected_interests", []))
    user_budget = user_input.get("budget", "unknown")

    pois_ref = db.collection("places").document(location).collection("poi_list")
    docs = pois_ref.stream()

    filtered_pois = []

    for doc in docs:
        data = doc.to_dict()

        # ✅ Normalize fields to avoid KeyErrors
        data.setdefault("tags", [])
        data.setdefault("budget_category", "unknown")
        data.setdefault("kid_friendly", None)
        data.setdefault("pet_friendly", None)
        data.setdefault("wheelchair_accessible", None)
        data.setdefault("disclaimer", "")
        data.setdefault("photo_url", "")
        data.setdefault("types", [])
        data.setdefault("coordinates", {})

        # ✅ Budget filter (only reject if explicitly mismatched)
        budget = data["budget_category"]
        if user_budget != "unknown" and budget != "unknown" and budget != user_budget:
            continue

        # ✅ Tag-based filtering (intersection with user interests)
        poi_tags = set(data["tags"])
        if user_tags and not poi_tags.intersection(user_tags):
            continue

        # ✅ Accessibility disclaimers (do NOT reject, only mark warnings)
        disclaimer = []
        
        # ✅ Check if family-friendly tag overrides kid_friendly field
        is_family_friendly = "family-friendly" in [tag.lower() for tag in data.get("tags", [])]
        
        if data["kid_friendly"] is False and not is_family_friendly:
            disclaimer.append("⚠️ Caution: may not be kid friendly")
        elif data["kid_friendly"] is True or is_family_friendly:
            disclaimer.append("✅ Suitable for kids")
        if user_input.get("with_pets") and data["pet_friendly"] is False:
            disclaimer.append("⚠️ No pets allowed")
        if user_input.get("with_disabilities") and data["wheelchair_accessible"] is False:
            disclaimer.append("⚠️ Not wheelchair accessible")

        data["disclaimer"] = " | ".join(disclaimer) if disclaimer else ""

        filtered_pois.append(data)

    print(f"✅ Filtered {len(filtered_pois)} POIs for location: {location}")
    return filtered_pois
