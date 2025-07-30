# itinerary_builder.py
from datetime import datetime, timedelta
import firebase_admin
from utils.firebase_utils import get_service_account_path  # ✅ Add this import
from firebase_admin import credentials, firestore
import os
import json

# Mapping tags to a rough "best time" description.  These are
# intentionally broad so the itinerary only suggests the general part
# of the day rather than a strict schedule.
TAG_TO_BEST_TIME = {
    "sunset": "Sunset",
    "sunrise": "Sunrise",
    "trek": "Morning",
    "shopping": "Afternoon",
    "romantic": "Evening",
    "culture": "Morning",
    "wildlife": "Morning",
    "religious": "Morning",
    "adventure": "Morning",
    "food": "Afternoon",
}

# ✅ Initialize Firestore once (reuse existing Firebase initialization logic)
def _get_firestore_client():
    """Get Firestore client, initializing Firebase if needed."""
    if not firebase_admin._apps:
        try:
            # ✅ Use your existing service account path resolver
            service_account_path = get_service_account_path()
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            print(f"❌ Failed to initialize Firebase: {e}")
            raise
    
    return firestore.client()

def fetch_hidden_gems_from_firebase(location, user_interests):
    """
    Fetch hidden gems from Firebase that match user interests and location.
    """
    try:
        db = _get_firestore_client()
        
        # ✅ Better location normalization
        location_normalized = location.lower().strip().replace(" ", "")
        user_tags = set(tag.lower() for tag in user_interests)
        
        print(f"🔍 Searching for hidden gems in '{location}' (normalized: '{location_normalized}') matching tags: {user_interests}")
        
        # ✅ Try multiple location variations
        possible_locations = [
            location.lower(),  # "bengaluru"
            location_normalized,  # "bengaluru" without spaces
            location.title(),  # "Bengaluru"
            
        ]
        
        matching_gems = []
        found_region = None
        
        # Try exact matches first
        for loc_variant in possible_locations:
            try:
                hidden_gems_ref = db.collection("hidden_gems").document(loc_variant).collection("gem_submissions")
                docs = list(hidden_gems_ref.where("status", "==", "approved").stream())
                if docs:
                    found_region = loc_variant
                    print(f"📍 Found exact match for region: '{loc_variant}'")
                    break
            except Exception as e:
                print(f"⚠️ Error checking location '{loc_variant}': {e}")
                continue
        
        # If no exact match, try fuzzy matching
        if not docs:
            print(f"🔍 No exact match found, trying fuzzy search...")
            try:
                all_regions = db.collection("hidden_gems").stream()
                for region_doc in all_regions:
                    region_name = region_doc.id.lower()
                    # ✅ Better fuzzy matching
                    if (any(part in region_name for part in location_normalized.split()) or
                        any(part in location_normalized for part in region_name.split()) or
                        location_normalized in region_name or
                        region_name in location_normalized):
                        
                        print(f"📍 Found fuzzy match: '{region_doc.id}' for location '{location}'")
                        hidden_gems_ref = region_doc.reference.collection("gem_submissions")
                        docs = list(hidden_gems_ref.where("status", "==", "approved").stream())
                        if docs:
                            found_region = region_doc.id
                            break
            except Exception as e:
                print(f"❌ Error during fuzzy search: {e}")
                return []
        
        if not docs:
            print(f"❌ No hidden gems found for location: {location}")
            return []
        
        # ✅ Process matching gems
        for doc in docs:
            try:
                data = doc.to_dict()
                if not data:
                    continue
                
                # Get gem tags and normalize them
                gem_tags = set(tag.lower() for tag in data.get("tags", []))
                
                # ✅ Check if there's any intersection between user interests and gem tags
                if user_tags.intersection(gem_tags):
                    # Determine best time based on tags
                    best_time = "Anytime"
                    for tag in data.get("tags", []):
                        if tag.lower() in TAG_TO_BEST_TIME:
                            best_time = TAG_TO_BEST_TIME[tag.lower()]
                            break
                    
                    # ✅ Safely get description and truncate
                    description = data.get("description", "Local Discovery")
                    truncated_desc = (description[:50] + "...") if len(description) > 50 else description
                    
                    gem = {
                        "name": f"🔍 Hidden Gem: {truncated_desc}",
                        "tags": data.get("tags", []),
                        "best_time": best_time,
                        "budget_category": data.get("budget_category", "unknown"),
                        "disclaimer": "🌟 Hidden gem suggested by locals",
                        "photo_url": data.get("image_urls", [""])[0] if data.get("image_urls") else "",
                        "coordinates": data.get("coordinates", {}),
                        "description": description,
                        "gem_id": doc.id,
                        "region": found_region
                    }
                    matching_gems.append(gem)
            except Exception as e:
                print(f"⚠️ Error processing gem document {doc.id}: {e}")
                continue
        
        print(f"✅ Found {len(matching_gems)} hidden gems matching user interests in {found_region}")
        return matching_gems
        
    except Exception as e:
        print(f"❌ Error fetching hidden gems for {location}: {e}")
        return []

# ...existing code...

def generate_itinerary(filtered_pois, start_date, end_date, enable_hidden_gems=False, max_per_day=2, location=None, user_interests=None):
    """
    Generate a scalable itinerary without attaching fixed dates.
    Distributes POIs across available days and includes disclaimers + photos.
    ``max_per_day`` controls how many POIs can be assigned to a single day.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    num_days = (end - start).days + 1

    # ✅ Instead of dates, we use day indices (Day 1, Day 2...)
    itinerary = {f"Day {i+1}": [] for i in range(num_days)}
    current_day_idx = 0
    current_day_count = 0
    day_keys = list(itinerary.keys())

    for poi in filtered_pois:
        if current_day_idx >= len(day_keys):
            break
        # Move to next day if the current one is filled
        if current_day_count >= max_per_day:
            current_day_idx += 1
            current_day_count = 0
            if current_day_idx >= len(day_keys):
                break

        # ✅ Determine best time to visit
        best_time = poi.get("best_time") or "Anytime"
        if best_time == "Anytime":
            for tag in poi.get("tags", []):
                if tag in TAG_TO_BEST_TIME:
                    best_time = TAG_TO_BEST_TIME[tag]
                    break

        activity = {
            "name": poi["name"],
            "tags": poi.get("tags", []),
            "best_time": best_time,
            "budget_category": poi.get("budget_category", "unknown"),
            "disclaimer": poi.get("disclaimer", ""),
            "photo_url": poi.get("photo_url", ""),
            "coordinates": poi.get("coordinates", {})  # ✅ For future route optimization
        }

        itinerary[day_keys[current_day_idx]].append(activity)
        current_day_count += 1

    # ✅ Add Hidden Gems from Firebase
    if enable_hidden_gems and location and user_interests:
        hidden_gems = fetch_hidden_gems_from_firebase(location, user_interests)
        
        if hidden_gems:
            # Add hidden gems to days that have space or create new slots
            gem_index = 0
            for day_key in day_keys:
                if gem_index >= len(hidden_gems):
                    break
                    
                # Add hidden gem if day has space (less than max_per_day)
                if len(itinerary[day_key]) < max_per_day:
                    itinerary[day_key].append(hidden_gems[gem_index])
                    gem_index += 1
        
        # Fallback: Add placeholder if no hidden gems found
        if not hidden_gems:
            for day in reversed(day_keys):
                if len(itinerary[day]) < max_per_day:
                    itinerary[day].append({
                        "name": "🔍 Hidden Gem (Coming Soon)",
                        "tags": ["surprise", "offbeat"],
                        "best_time": "Anytime",
                        "disclaimer": "⏳ No hidden gems found for your interests in this location. Feature expanding!"
                    })
                    break

    return itinerary
