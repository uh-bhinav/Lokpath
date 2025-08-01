# itinerary_builder.py
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import os
import dateutil.parser

def _get_firestore_client():
    """Get Firestore client, initializing Firebase if needed."""
    if not firebase_admin._apps:
        try:
            # ✅ Use the EXACT same path as test_firebase.py which works
            FIREBASE_SERVICE_ACCOUNT_PATH = "../credentials/lokpath-2d9a0-firebase-adminsdk-fbsvc-cd5812102d.json"
            
            # Check if file exists
            if os.path.exists(FIREBASE_SERVICE_ACCOUNT_PATH):
                cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase initialized successfully")
                
                # Print project info for verification
                import json
                with open(FIREBASE_SERVICE_ACCOUNT_PATH, 'r') as f:
                    creds_data = json.load(f)
                print(f"📊 Connected to project: {creds_data.get('project_id')}")
                
            else:
                print(f"❌ Firebase credentials not found at: {FIREBASE_SERVICE_ACCOUNT_PATH}")
                raise FileNotFoundError(f"Firebase credentials not found")
                
        except Exception as e:
            print(f"❌ Failed to initialize Firebase: {e}")
            raise
    
    return firestore.client()

def test_firebase_connection():
    """Test basic Firebase connection"""
    try:
        db = _get_firestore_client()
        
        # Test basic Firestore access
        print("🧪 Testing Firebase connection...")
        
        # Try to access a simple collection
        test_ref = db.collection("hidden_gems")
        print(f"✅ Successfully accessed hidden_gems collection reference")
        
        # Try to list documents (this will show permission issues)
        docs = list(test_ref.limit(1).stream())
        print(f"✅ Successfully retrieved documents: {len(docs)} found")
        
        return True
        
    except Exception as e:
        print(f"❌ Firebase connection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

# Test the connection first
# Note: These tests will run only if the file is executed directly
# Move the actual test calls to the bottom of the file


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

# Debugging Firebase structure
def debug_firebase_structure():
    """Debug function to understand the actual Firebase structure"""
    try:
        db = _get_firestore_client()
        
        print("🔍 Debugging Firebase structure...")
        
        # ✅ First test: Can we access the collection at all?
        try:
            hidden_gems_ref = db.collection("hidden_gems")
            print("✅ Successfully got hidden_gems collection reference")
        except Exception as e:
            print(f"❌ Failed to get collection reference: {e}")
            return
        
        # ✅ Use list_documents instead of stream (this is the key fix!)
        try:
            state_refs = list(hidden_gems_ref.list_documents())  # Changed from stream() to list_documents()
            print(f"📊 Found {len(state_refs)} state document references")
        except Exception as e:
            print(f"❌ Failed to list document references: {e}")
            print("💡 This usually indicates a permissions issue")
            return
        
        # Process each state reference
        for state_ref in state_refs:
            print(f"\n🏛️ State: {state_ref.id}")
            
            try:
                # Check if document has data
                state_doc = state_ref.get()
                if state_doc.exists:
                    data = state_doc.to_dict()
                    if data:
                        print(f"  📋 Document has data: {list(data.keys())}")
                    else:
                        print(f"  📝 Document exists but has no data")
                else:
                    print(f"  ❌ Document reference exists but document is empty")
                
                # Check subcollections
                subcollections = state_ref.collections()
                subcol_names = [col.id for col in subcollections]
                if subcol_names:
                    print(f"  📁 Subcollections: {subcol_names}")
                    
                    # Check cities specifically
                    if "cities" in subcol_names:
                        cities_ref = state_ref.collection("cities")
                        city_refs = list(cities_ref.list_documents())
                        print(f"    �️ Cities: {[city.id for city in city_refs]}")
                        
                        # Check Bengaluru specifically
                        for city_ref in city_refs:
                            if city_ref.id.lower() in ["bengaluru", "bangalore"]:
                                print(f"    🎯 Found {city_ref.id}! Checking gems...")
                                
                                try:
                                    gems_ref = city_ref.collection("gem_submissions")
                                    gem_docs = list(gems_ref.stream())
                                    print(f"      💎 Found {len(gem_docs)} gems")
                                    
                                    for gem_doc in gem_docs:
                                        gem_data = gem_doc.to_dict()
                                        print(f"        ✨ {gem_doc.id}: Status={gem_data.get('status')}, Tags={gem_data.get('tags')}")
                                        
                                except Exception as gem_e:
                                    print(f"      ❌ Error accessing gems: {gem_e}")
                else:
                    print(f"  📁 No subcollections found")
                        
            except Exception as e:
                print(f"  ❌ Error accessing state {state_ref.id}: {e}")
                
        print("\n" + "="*50)
        
    except Exception as e:
        print(f"❌ Error debugging Firebase: {e}")
        import traceback
        traceback.print_exc()

# ✅ Initialize Firestore once (reuse existing Firebase initialization logic)
# This duplicate function is removed to avoid conflicts


# -----------------------------------------------------------------------------
# NOTE: This function assumes that:
# 1. The `location` parameter passed in is a city name (e.g., "Bengaluru").
# 2. Firestore follows the hierarchy: hidden_gems/{state}/cities/{city}/gem_submissions.
# 3. Hidden gems are only considered if their `status` field is "verified".
# 4. User interests (`user_interests`) are expected to be a list of tags for matching.
# 5. Matching is done by normalizing city names to lowercase and removing spaces.
# 6. Only gems whose tags intersect with user interests are included in the output.
# 7. If no city matches, the function does NOT fall back to state-level or global search.
# -----------------------------------------------------------------------------


def fetch_hidden_gems_from_firebase(location, user_interests):
    """
    Fetch hidden gems from Firebase that match user interests and location.
    Uses direct path access since state documents don't exist as documents.
    """
    try:
        db = _get_firestore_client()

        # ✅ Normalize user input
        location_normalized = location.lower().strip().replace(" ", "")
        user_tags = set(tag.lower() for tag in user_interests)
        print(f"🔍 Searching for hidden gems in '{location}' matching tags: {user_interests}")

        matching_gems = []

        # ✅ Enhanced location matching with common aliases
        location_variants = [
            location.lower(),
            location_normalized,
            location.title(),
            location.upper(),
        ]
        
        # Add common city aliases
        if "bengaluru" in location.lower():
            location_variants.extend(["bangalore", "bengalooru"])
        elif "bangalore" in location.lower():
            location_variants.extend(["bengaluru", "bengalooru"])

        print(f"🔍 Trying location variants: {location_variants}")

        # ✅ Get all state document references (they may not have data but have subcollections)
        try:
            hidden_gems_ref = db.collection("hidden_gems")
            state_refs = list(hidden_gems_ref.list_documents())  # Use list_documents instead of stream
            print(f"📊 Found {len(state_refs)} state document references")
            
            for state_ref in state_refs:
                state_id = state_ref.id
                print(f"🏛️ Checking state: {state_id}")
                
                try:
                    # Check cities subcollection
                    cities_ref = state_ref.collection("cities")
                    city_refs = list(cities_ref.list_documents())
                    print(f"   📍 Found {len(city_refs)} city references")
                    
                    for city_ref in city_refs:
                        city_id = city_ref.id
                        print(f"      🏙️ Checking city: {city_id}")
                        
                        # Check if this city matches any of our location variants
                        city_match = False
                        for variant in location_variants:
                            variant_norm = variant.lower().replace(" ", "")
                            city_norm = city_id.lower().replace(" ", "")
                            if (variant_norm in city_norm or 
                                city_norm in variant_norm or
                                variant_norm == city_norm):
                                city_match = True
                                print(f"         ✅ City match: '{variant}' matches '{city_id}'")
                                break
                        
                        if city_match:
                            try:
                                # Get gems from this city
                                gems_ref = city_ref.collection("gem_submissions")
                                verified_docs = list(gems_ref.where("status", "==", "verified").stream())
                                print(f"         💎 Found {len(verified_docs)} verified gems")
                                
                                for gem_doc in verified_docs:
                                    try:
                                        data = gem_doc.to_dict()
                                        if not data:
                                            continue

                                        # Get gem tags and check intersection
                                        gem_tags_raw = data.get("tags", [])
                                        if isinstance(gem_tags_raw, str):
                                            gem_tags_raw = [gem_tags_raw]
                                        
                                        gem_tags = set(tag.lower().strip() for tag in gem_tags_raw if tag)
                                        
                                        print(f"         🏷️ Gem {gem_doc.id}: tags={gem_tags_raw}")

                                        # Only include if tags intersect with user interests
                                        tag_intersection = user_tags.intersection(gem_tags)
                                        if tag_intersection:
                                            print(f"            ✅ Tag match found: {tag_intersection}")
                                            
                                            # Determine best time
                                            best_time = data.get("best_time", "Anytime")
                                            if best_time == "Anytime" or not best_time:
                                                for tag in gem_tags_raw:
                                                    if tag.lower() in TAG_TO_BEST_TIME:
                                                        best_time = TAG_TO_BEST_TIME[tag.lower()]
                                                        break
                                            
                                            description = data.get("description", "Local Discovery")
                                            truncated_desc = (description[:50] + "...") if len(description) > 50 else description

                                            # Handle coordinates
                                            coordinates = data.get("coordinates", {})
                                            if isinstance(coordinates, dict) and "lat" in coordinates and "lng" in coordinates:
                                                coords = coordinates
                                            elif isinstance(coordinates, dict) and "latitude" in coordinates and "longitude" in coordinates:
                                                coords = {"lat": coordinates["latitude"], "lng": coordinates["longitude"]}
                                            else:
                                                coords = {}

                                            gem = {
                                                "name": f"🔍 Hidden Gem: {truncated_desc}",
                                                "tags": gem_tags_raw,
                                                "best_time": best_time,
                                                "budget_category": data.get("budget_category", "unknown"),
                                                "disclaimer": "🌟 Hidden gem suggested by locals",
                                                "photo_url": data.get("image_urls", [""])[0] if data.get("image_urls") else "",
                                                "coordinates": coords,
                                                "description": description,
                                                "gem_id": gem_doc.id,
                                                "city_name": data.get("city_name", ""),
                                                "state_name": data.get("state_name", ""),
                                                "region": f"{state_id}/{city_id}",
                                                "status": data.get("status", "unknown")
                                            }
                                            matching_gems.append(gem)
                                            print(f"            ✅ Added to final list: {truncated_desc}")
                                        else:
                                            print(f"            ❌ No tag intersection for gem {gem_doc.id}")

                                    except Exception as e:
                                        print(f"         ⚠️ Error processing gem {gem_doc.id}: {e}")
                                        continue
                                        
                            except Exception as e:
                                print(f"      ❌ Error accessing gems in {city_id}: {e}")
                                continue
                                
                except Exception as e:
                    print(f"   ❌ Error accessing cities in {state_id}: {e}")
                    continue
                    
        except Exception as e:
            print(f"❌ Error accessing hidden_gems collection: {e}")
            return []

        print(f"🎉 Final result: {len(matching_gems)} hidden gems matching user interests")
        return matching_gems

    except Exception as e:
        print(f"❌ Critical error fetching hidden gems for {location}: {e}")
        import traceback
        traceback.print_exc()
        return []

def generate_itinerary(filtered_pois, start_date, end_date, enable_hidden_gems=False, max_per_day=2, location=None, user_interests=None):
    """
    Generate a scalable itinerary without attaching fixed dates.
    Distributes POIs across available days and includes disclaimers + photos.
    ``max_per_day`` controls how many POIs can be assigned to a single day.
    """
    start = dateutil.parser.isoparse(start_date)
    end = dateutil.parser.isoparse(end_date)
    num_days = (end - start).days + 1

    # ✅ Fetch hidden gems first to know how many we have
    hidden_gems = []
    if enable_hidden_gems and location and user_interests:
        hidden_gems = fetch_hidden_gems_from_firebase(location, user_interests)
        print(f"🎯 Found {len(hidden_gems)} hidden gems to integrate")

    # ✅ Adjust max_per_day to accommodate hidden gems
    regular_poi_limit = max_per_day
    effective_max_per_day = max_per_day
    
    if hidden_gems:
        # Reserve space for hidden gems by keeping regular POI limit at original value
        # but increase total capacity
        effective_max_per_day = max_per_day + 1
        print(f"📈 Increased daily POI limit from {max_per_day} to {effective_max_per_day} to accommodate hidden gems")
        print(f"🎯 Regular POIs will use {regular_poi_limit} slots, hidden gems will use the extra slot")
    else:
        regular_poi_limit = max_per_day

    # ✅ Instead of dates, we use day indices (Day 1, Day 2...)
    itinerary = {f"Day {i+1}": [] for i in range(num_days)}
    current_day_idx = 0
    current_day_count = 0
    day_keys = list(itinerary.keys())

    for poi in filtered_pois:
        if current_day_idx >= len(day_keys):
            break
        # Move to next day if the current one is filled (use regular_poi_limit to reserve space for hidden gems)
        if current_day_count >= regular_poi_limit:
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
    if hidden_gems:
        print(f"🌟 Integrating {len(hidden_gems)} hidden gems into itinerary...")
        print(f"📊 Current itinerary state before adding gems:")
        for day_key in day_keys:
            print(f"   {day_key}: {len(itinerary[day_key])} activities (max allowed: {effective_max_per_day})")
        
        # Add hidden gems to days that have space
        gem_index = 0
        for day_key in day_keys:
            if gem_index >= len(hidden_gems):
                break
                
            # Add hidden gem if day has space (less than effective_max_per_day)
            current_activities = len(itinerary[day_key])
            print(f"   🔍 Checking {day_key}: {current_activities} activities, limit: {effective_max_per_day}")
            
            if current_activities < effective_max_per_day:
                gem = hidden_gems[gem_index]
                print(f"   ✨ Adding '{gem['name']}' to {day_key}")
                itinerary[day_key].append(gem)
                gem_index += 1
            else:
                print(f"   ❌ {day_key} is full ({current_activities}/{effective_max_per_day})")
                
        # If we still have unassigned gems, try to add them to days with the least activities
        remaining_gems = hidden_gems[gem_index:]
        if remaining_gems:
            print(f"   🔄 Adding {len(remaining_gems)} remaining gems to least busy days...")
            # Sort days by number of activities (ascending)
            sorted_days = sorted(day_keys, key=lambda d: len(itinerary[d]))
            print(f"   📊 Day activity counts: {[(d, len(itinerary[d])) for d in sorted_days]}")
            
            for gem in remaining_gems:
                for day_key in sorted_days:
                    if len(itinerary[day_key]) < effective_max_per_day:
                        print(f"   ✨ Adding overflow gem '{gem['name']}' to {day_key}")
                        itinerary[day_key].append(gem)
                        break
                else:
                    print(f"   ❌ Could not find space for gem '{gem['name']}' - all days are full!")
    else:
        # Fallback: Add placeholder if no hidden gems found
        if enable_hidden_gems:
            for day in reversed(day_keys):
                if len(itinerary[day]) < effective_max_per_day:
                    itinerary[day].append({
                        "name": "🔍 Hidden Gem (Coming Soon)",
                        "tags": ["surprise", "offbeat"],
                        "best_time": "Anytime",
                        "disclaimer": "⏳ No hidden gems found for your interests in this location. Feature expanding!"
                    })
                    break

    return itinerary

# ✅ Test functions - only run when file is executed directly
if __name__ == "__main__":
    print("🚀 Running Firebase tests...")
    if test_firebase_connection():
        debug_firebase_structure()
    else:
        print("❌ Skipping debug due to connection failure")

