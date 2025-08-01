# itinerary_generator/routes.py
from flask import Blueprint, request, jsonify, session, current_app
from firebase_admin import firestore
from user_auth.utils import login_required_user
import datetime
import dateutil.parser
import uuid
from flask import Blueprint, request, jsonify, session, current_app
from firebase_admin import firestore
from user_auth.utils import login_required_user
import datetime
import uuid
# --- Import all of your teammate's modules ---
from Itinerarybuilder.itinerary_builder import generate_itinerary, TAG_TO_BEST_TIME
from Itinerarybuilder.query_firestore import get_filtered_pois
from Itinerarybuilder.fetch_places import fetch_places
from Itinerarybuilder.get_reviews import get_reviews_for_place
from Itinerarybuilder.tag_reviews import tag_place_with_reviews, has_kid_friendly_issues
from Itinerarybuilder.store_firestore import store_itinerary
from Itinerarybuilder.store_pois import store_pois
from Itinerarybuilder.utils.itinerary_utils import estimate_required_pois, infer_kid_friendly
from Itinerarybuilder.utils.place_info import map_price_level
from shared_globals import session_store # Ensure session_store is imported if needed elsewhere

def create_itinerary_bp(db_instance): # Function to create and return the blueprint
    itinerary_bp = Blueprint('itinerary_bp', __name__, url_prefix='/itinerary')

    @itinerary_bp.route('/generate', methods=['POST'])
    @login_required_user # Only authenticated users can generate itineraries
    def generate_itinerary_route():
        user_uid = session.get('user_uid')
        if not user_uid:
            current_app.logger.error("User UID not found in session for itinerary generation.")
            return jsonify({"error": "Authentication error."}), 500

        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing request body for itinerary generation."}), 400

        # --- Input Validation (Crucial for any API endpoint) ---
        required_fields = ['start_date', 'end_date', 'num_people', 'interests', 'budget_level', 'location']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        if not isinstance(data['num_people'], int) or data['num_people'] <= 0:
            return jsonify({"error": "num_people must be a positive integer."}), 400
        if not isinstance(data['interests'], list) or not all(isinstance(i, str) for i in data['interests']):
            return jsonify({"error": "interests must be a list of strings."}), 400
        if data['budget_level'] not in ['low', 'mid', 'high']:
            return jsonify({"error": "budget_level must be 'low', 'mid', or 'high'."}), 400

        # Calculate days of travel
        try:
            # Handle 'Z' suffix for UTC ISO format if present
            start_date = dateutil.parser.isoparse(data['start_date'])
            end_date = dateutil.parser.isoparse(data['end_date'])
            if end_date < start_date:
                return jsonify({"error": "end_date cannot be before start_date."}), 400
            days_of_travel = (end_date - start_date).days + 1
            data['days_of_travel'] = days_of_travel
        except ValueError:
            return jsonify({"error": "start_date and end_date must be valid ISO format dates (YYYY-MM-DDTHH:MM:SS.sssZ)."}), 400
        
        user_input = {
            "user_id": user_uid,
            "start_date": data['start_date'],
            "end_date": data['end_date'],
            "num_people": data['num_people'],
            "interests": data['interests'],
            "budget_level": data['budget_level'],
            "location": data['location'],
            "disabilities_toggle": data.get('disabilities_toggle', False),
            "kids_toggle": data.get('kids_toggle', False),
            "pets_toggle": data.get('pets_toggle', False),
            "days_of_travel": days_of_travel
        }

        # --- Call the AI engine here ---
        try:
            current_app.logger.info(f"Orchestrating itinerary pipeline for user {user_uid}...")

            # Step 1: Estimate POIs required based on trip length
            required_pois = estimate_required_pois(user_input["start_date"], user_input["end_date"])

            # Step 2: Query Firestore for existing POIs
            # This call uses the `db` client from our Flask app
            filtered_pois = get_filtered_pois(user_input)

            # Step 3: Fallback to Google Places if insufficient POIs
            if len(filtered_pois) < required_pois:
                current_app.logger.info(f"⚠️ Only {len(filtered_pois)} POIs found, but {required_pois} needed. Fetching additional POIs...")
                new_places = fetch_places(user_input["location"])

                for place in new_places:
                    reviews = get_reviews_for_place(place["place_id"])
                    tags = tag_place_with_reviews(place["name"], reviews)
                    kid_warning = has_kid_friendly_issues(reviews)

                    place["tags"] = tags
                    place["budget_category"] = map_price_level(place.get("price_level"))
                    if kid_warning:
                        place["kid_friendly"] = False
                    else:
                        place["kid_friendly"] = infer_kid_friendly(tags) if infer_kid_friendly(tags) is not None else False
                    place.setdefault("pet_friendly", False)
                    place.setdefault("wheelchair_accessible", False)
                    place.setdefault("disclaimer", "")

                store_pois(user_input["location"], new_places)
                filtered_pois = get_filtered_pois(user_input)

            # Step 4: Generate itinerary
            itinerary_data = generate_itinerary(
                filtered_pois,
                user_input["start_date"],
                user_input["end_date"],
                enable_hidden_gems=True,
                location=user_input["location"],
                user_interests=user_input["interests"]
            )

            # Step 5: Store final itinerary
            trip_id = str(uuid.uuid4())
            store_itinerary(
                user_input["user_id"],
                user_input["location"],
                user_input["start_date"],
                user_input["end_date"],
                itinerary_data,
                trip_id
            )

            current_app.logger.info(f"Itinerary {trip_id} generated and stored for user {user_uid}.")

            return jsonify({
                "message": "Itinerary generated successfully!",
                "itinerary_id": trip_id,
                "itinerary": itinerary_data
            }), 201

        except Exception as e:
            current_app.logger.error(f"Error in itinerary generation pipeline for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to generate itinerary.", "details": str(e)}), 500
            
    @itinerary_bp.route('/<itinerary_id>', methods=['GET'])
    @login_required_user
    def get_itinerary(itinerary_id):
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication error."}), 401

        itinerary_ref = db_instance.collection('users').document(user_uid).collection('itineraries').document(itinerary_id)
        itinerary_doc = itinerary_ref.get()

        if itinerary_doc.exists:
            return jsonify({"message": "Itinerary retrieved successfully", "itinerary": itinerary_doc.to_dict()}), 200
        else:
            return jsonify({"error": "Itinerary not found."}), 404

    @itinerary_bp.route('/my_itineraries', methods=['GET'])
    @login_required_user
    def get_my_itineraries():
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication error."}), 401

        itineraries = []
        docs = db_instance.collection('users').document(user_uid).collection('itineraries').stream()
        for doc in docs:
            itineraries.append(doc.to_dict())

        itineraries.sort(key=lambda x: x.get('generated_at', firestore.SERVER_TIMESTAMP), reverse=True)

        return jsonify({"message": "User itineraries retrieved successfully", "itineraries": itineraries}), 200

    return itinerary_bp