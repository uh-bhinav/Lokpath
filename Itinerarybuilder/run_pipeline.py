# run_pipeline.py

from dotenv import load_dotenv
import uuid

# Load environment variables at the very beginning
load_dotenv()

from query_firestore import get_filtered_pois
from fetch_places import fetch_places
from get_reviews import get_reviews_for_place
from tag_reviews import tag_place_with_reviews, has_kid_friendly_issues
from itinerary_builder import generate_itinerary # This is your new, smart generator
from store_firestore import store_itinerary
from store_pois import store_pois
from utils.itinerary_utils import estimate_required_pois, infer_kid_friendly
from utils.place_info import map_price_level

# --- Step 0: Define User Input with Pacing Preferences ---
# This dictionary now drives the entire intelligent generation process.
user_input = {
    "user_id": "user_123",
    "location": "Bengaluru",
    "start_date": "2025-10-10",
    "end_date": "2025-10-12", # A 3-day trip
    "selected_interests": ["historical", "local food", "nature", "peaceful"],
    "budget": "mid",
    "with_kids": False,
    "with_pets": False,
    "with_disabilities": False,
    # User preferences for pacing the trip
    "trip_pace": "moderate",  # Options: 'relaxed', 'moderate', 'packed'
    "travel_style": "leisurely" # Options: 'leisurely', 'efficient'
}

# --- Step 1: Estimate POIs Required (Initial Check) ---
# This helps decide if we need to fetch new data from Google.
required_pois = estimate_required_pois(user_input["start_date"], user_input["end_date"])

# --- Step 2: Query Firestore for a Broad Set of POIs ---
# Your modified get_filtered_pois now fetches a wide range of candidates to be scored.
filtered_pois = get_filtered_pois(user_input)

# --- Step 3: Fallback to Google Places to Enrich Your Database ---
# This block runs only if your database doesn't have enough POIs for the location.
if len(filtered_pois) < required_pois:
    print(f"⚠️ Only {len(filtered_pois)} POIs found, but {required_pois} needed.")
    print("📥 Fetching additional POIs from Google Places to enrich the database...")

    new_places = fetch_places(user_input["location"])

    for place in new_places:
        reviews = get_reviews_for_place(place["place_id"])
        
        # Get tags and intensity from the review model
        tag_results = tag_place_with_reviews(place["name"], reviews)
        
        # Normalize all data for consistent storage in Firestore
        place["tags"] = tag_results.get("tags", [])
        place["intensity"] = tag_results.get("intensity", "medium")
        place["budget_category"] = map_price_level(place.get("price_level"))
        
        kid_warning = has_kid_friendly_issues(reviews)
        if kid_warning:
            place["kid_friendly"] = False
        else:
            place["kid_friendly"] = True if infer_kid_friendly(place["tags"]) is True else None
        
        place.setdefault("pet_friendly", None)
        place.setdefault("wheelchair_accessible", None)

    # Save the newly enriched POIs to Firestore for future use
    store_pois(user_input["location"], new_places)

    # Re-query to get the complete and fresh list for the user
    filtered_pois = get_filtered_pois(user_input)

# --- Step 4: Generate the Smart Itinerary ---
# This is the main call that uses all the new logic.

# First, map user's preferences to concrete budget values
time_budgets = {"relaxed": 6.0, "moderate": 7.5, "packed": 9.0}
travel_caps = {"leisurely": 2.0, "efficient": 3.5}

activity_budget = time_budgets.get(user_input.get("trip_pace"), 7.5)
travel_budget = travel_caps.get(user_input.get("travel_style"), 2.0)

# Call the new, intelligent generate_itinerary function
itinerary = generate_itinerary(
    filtered_pois=filtered_pois,
    start_date=user_input["start_date"],
    end_date=user_input["end_date"],
    user_input=user_input, # Pass the full user_input for scoring
    # daily_time_budget=activity_budget,
    # max_daily_travel_hours=travel_budget,
    enable_hidden_gems=True
)

# --- Step 5: Store the Final Itinerary ---
trip_id = str(uuid.uuid4())
store_itinerary(
    user_id=user_input["user_id"],
    location=user_input["location"],
    start_date=user_input["start_date"],
    end_date=user_input["end_date"],
    itinerary=itinerary,
    trip_id=trip_id
)

# --- Step 6: Print a Summary of the Generated Plan ---
print("\n" + "="*50)
print(f"✅ SMART ITINERARY GENERATED for {user_input['location']}")
print(f"   Pace: {user_input['trip_pace']} | Travel Style: {user_input['travel_style']}")
print("="*50)

for day, activities in itinerary.items():
    print(f"\n📅 {day}")
    if not activities:
        print("  (A day to relax and explore freely!)")
    else:
        for a in activities:
            score = a.get('match_score', 0)
            duration = a.get('estimated_visit_duration', 0)
            print(
                f"  - {a['name']} (Score: {score:.1f}, Duration: {duration}h)"
            )