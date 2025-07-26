# query_firestore.py

import firebase_admin
from firebase_admin import credentials, firestore

# ✅ Initialize Firestore once
if not firebase_admin._apps:
    cred = credentials.Certificate("credentials/lokpath-2d9a0-firebase-adminsdk-fbsvc-cd5812102d.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def get_filtered_pois(user_input):
    """
    Fetch and filter POIs from Firestore for a given location.
    Applies budget, interest tags, and accessibility filters.
    ✅ Safe for scaling.
    ✅ Works with both Google POIs and hidden gems.
    """
    location = user_input["location"]
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
        data.setdefault("kid_friendly", False)
        data.setdefault("pet_friendly", False)
        data.setdefault("wheelchair_accessible", False)
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
        if user_input.get("with_kids") and not data["kid_friendly"]:
            disclaimer.append("⚠️ Not suitable for kids")
        if user_input.get("with_pets") and not data["pet_friendly"]:
            disclaimer.append("⚠️ No pets allowed")
        if user_input.get("with_disabilities") and not data["wheelchair_accessible"]:
            disclaimer.append("⚠️ Not wheelchair accessible")

        data["disclaimer"] = " | ".join(disclaimer) if disclaimer else ""

        filtered_pois.append(data)

    print(f"✅ Filtered {len(filtered_pois)} POIs for location: {location}")
    return filtered_pois
