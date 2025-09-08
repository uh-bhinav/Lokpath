# itinerary_generator/routes.py
from flask import Blueprint, request, jsonify, session, current_app
from firebase_admin import firestore
from user_auth.utils import login_required_user
import datetime
import dateutil.parser
import uuid

from itinerary_generator.utils import ranking_utils, suggestion_utils, normalization_utils
# from itinerary_generator.utils.firestore_utils import get_places_for_location
# from itinerary_generator.utils.google_places_utils import fetch_places_from_google
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
from Itinerarybuilder.fetch_places import search_places_autocomplete, get_place_details
from utils.place_info import load_google_api_key

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

    @itinerary_bp.route('/<itinerary_id>/book-guide', methods=['POST'])
    @login_required_user
    def book_guide_for_itinerary(itinerary_id):
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required."}), 401

        data = request.get_json()
        guide_id = data.get('guide_id')

        if not guide_id:
            return jsonify({"error": "Missing required field: guide_id."}), 400

        try:
            # 1. Verify the itinerary exists and belongs to the user
            itinerary_ref = db_instance.collection('users').document(user_uid).collection('itineraries').document(itinerary_id)
            itinerary_doc = itinerary_ref.get()
            if not itinerary_doc.exists:
                return jsonify({"error": "Itinerary not found for this user."}), 404

            itinerary_data = itinerary_doc.to_dict()

            # 2. Verify the guide exists and is approved
            guide_ref = db_instance.collection('guides').document(guide_id)
            guide_doc = guide_ref.get()
            if not guide_doc.exists or guide_doc.to_dict().get('status') != 'approved':
                return jsonify({"error": "Requested guide not found or not approved."}), 404

            # 3. Create a new booking document in Firestore
            booking_id = str(uuid.uuid4())
            booking_data = {
                "booking_id": booking_id,
                "tourist_uid": user_uid,
                "assigned_guide_uid": guide_id,
                "itinerary_id": itinerary_id, # Link the booking to the itinerary
                "itinerary_location": itinerary_data.get('input_preferences', {}).get('location'),
                "start_date": itinerary_data.get('input_preferences', {}).get('start_date'),
                "end_date": itinerary_data.get('input_preferences', {}).get('end_date'),
                "request_timestamp": firestore.SERVER_TIMESTAMP,
                "status": "pending_acceptance", # Assuming a pending state for the guide to accept
                "message_to_guide": data.get('message_to_guide', "")
            }

            db_instance.collection('bookings').document(booking_id).set(booking_data)

            current_app.logger.info(f"Booking request {booking_id} created for itinerary {itinerary_id} by {user_uid}.")

            # 4. Update the itinerary document to show it has a guide booked
            itinerary_ref.update({
                "guide_booked_uid": guide_id,
                "booking_id": booking_id,
                "status": "booked"
            })
            current_app.logger.info(f"Itinerary {itinerary_id} status updated to 'booked'.")

            return jsonify({
                "message": "Guide booking request submitted successfully!",
                "booking_id": booking_id,
                "itinerary_id": itinerary_id,
                "assigned_guide_uid": guide_id
            }), 201

        except Exception as e:
            current_app.logger.error(f"Error booking guide for itinerary {itinerary_id} for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to book guide for itinerary.", "details": str(e)}), 500

    @itinerary_bp.route('/<itinerary_id>/book-guide/segments', methods=['POST'])
    @login_required_user
    def book_guide_for_itinerary_segments(itinerary_id):
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required."}), 401

        data = request.get_json()
        guide_id = data.get('guide_id')
        segments = data.get('segments') # A list of {'day': 1, 'poi_name': '...'}
        message_to_guide = data.get('message_to_guide', "")

        if not guide_id or not segments:
            return jsonify({"error": "Missing required fields: guide_id and segments."}), 400

        if not isinstance(segments, list) or not all('day' in s and 'poi_name' in s for s in segments):
            return jsonify({"error": "Segments must be a list of objects with 'day' and 'poi_name'."}), 400

        try:
            # 1. Verify the itinerary exists and belongs to the user
            itinerary_ref = db_instance.collection('users').document(user_uid).collection('itineraries').document(itinerary_id)
            itinerary_doc = itinerary_ref.get()
            if not itinerary_doc.exists:
                return jsonify({"error": "Itinerary not found for this user."}), 404

            itinerary_data = itinerary_doc.to_dict()

            # 2. Verify the guide exists and is approved
            guide_ref = db_instance.collection('guides').document(guide_id)
            guide_doc = guide_ref.get()
            if not guide_doc.exists or guide_doc.to_dict().get('status') != 'approved':
                return jsonify({"error": "Requested guide not found or not approved."}), 404

            # 3. Create a new booking document for the segments
            booking_id = str(uuid.uuid4())
            booking_data = {
                "booking_id": booking_id,
                "tourist_uid": user_uid,
                "assigned_guide_uid": guide_id,
                "itinerary_id": itinerary_id,
                "itinerary_segments": segments, # Store the specific segments
                "booking_type": "per_segment",
                "request_timestamp": firestore.SERVER_TIMESTAMP,
                "status": "pending_acceptance",
                "message_to_guide": message_to_guide
            }

            db_instance.collection('bookings').document(booking_id).set(booking_data)

            current_app.logger.info(f"Segment booking {booking_id} created for itinerary {itinerary_id} by {user_uid}.")

            # 4. Update the itinerary document to show it has a guide booked for specific parts
            itinerary_ref.update({
                "guide_booked_uid": guide_id,
                "booking_id": booking_id,
                "status": "booked"
            })
            current_app.logger.info(f"Itinerary {itinerary_id} status updated to 'booked' for specific segments.")

            return jsonify({
                "message": "Guide booking request for itinerary segments submitted successfully!",
                "booking_id": booking_id,
                "itinerary_id": itinerary_id,
                "assigned_guide_uid": guide_id
            }), 201

        except Exception as e:
            current_app.logger.error(f"Error booking guide for itinerary segments {itinerary_id} for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to book guide for itinerary segments.", "details": str(e)}), 500


    @itinerary_bp.route('/<itinerary_id>/days/<int:day_number>/items/<int:item_index>', methods=['DELETE'])
    @login_required_user
    def delete_itinerary_item(itinerary_id, day_number, item_index):
            """Delete a single POI from a specific day in the itinerary by index.
            - Path: /itinerary/<itinerary_id>/days/<day_number>/items/<item_index>
            - Day numbering is 1-based (matches 'Day 1', 'Day 2', ...)
            - Only removes the specified POI; other POIs remain untouched.
            """
            user_uid = session.get('user_uid')
            if not user_uid:
                return jsonify({"error": "Authentication required."}), 401

            try:
                # 1) Locate itinerary doc under unified path: /users/{uid}/itineraries/{itinerary_id}
                doc_ref = db_instance.collection('users').document(user_uid) \
                    .collection('itineraries').document(itinerary_id)
                snap = doc_ref.get()
                if not snap.exists:
                    return jsonify({"error": "Itinerary not found for this user."}), 404

                doc = snap.to_dict() or {}
                itinerary = doc.get('itinerary', {})
                if not isinstance(itinerary, dict) or not itinerary:
                    return jsonify({"error": "Invalid itinerary structure."}), 400

                # 2) Resolve day key and validate index
                day_key = f"Day {day_number}"
                day_list = itinerary.get(day_key)
                if not isinstance(day_list, list):
                    return jsonify({"error": f"{day_key} not found."}), 404
                if item_index < 0 or item_index >= len(day_list):
                    return jsonify({"error": f"item_index {item_index} out of range for {day_key}."}), 400

                # 3) Remove only the targeted POI
                removed = day_list.pop(item_index)
                itinerary[day_key] = day_list

                # 4) Recompute poi_count and persist the update
                poi_count = sum(len(day) for day in itinerary.values())
                doc_ref.update({
                    'itinerary': itinerary,
                    'poi_count': poi_count,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })

                return jsonify({
                    'message': 'POI deleted from itinerary',
                    'itinerary_id': itinerary_id,
                    'day': day_key,
                    'removed': removed,
                    'poi_count': poi_count,
                    'itinerary': itinerary
                }), 200

            except Exception as e:
                current_app.logger.error(f"Failed to delete item from itinerary {itinerary_id}: {e}", exc_info=True)
                return jsonify({"error": "Failed to delete item.", "details": str(e)}), 500



    @itinerary_bp.route('/<itinerary_id>/replenish-missing-pois', methods=['POST'])
    @login_required_user
    def replenish_missing_pois(itinerary_id):
        """Replenish missing POIs after deletions, then re-optimize by proximity.
        Logic:
          - Compute required_total = num_days * max_per_day
          - If current < required, fetch candidate POIs for the same location
          - Deduplicate vs existing, take first `missing` items
          - Append to itinerary, persist, then call optimizer
          - Return final optimized itinerary with counts
        """
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required."}), 401

        body = request.get_json(silent=True) or {}
        dry_run = bool(body.get('dry_run', False))
        limit_factor = int(body.get('limit_factor', 2))
        if limit_factor < 1:
            limit_factor = 1

        try:
            # Helpers (kept local for reliability)
            def _poi_key(poi: dict) -> str:
                pid = poi.get('place_id') or poi.get('google_place_id')
                if pid:
                    return f"id:{pid}"
                name = (poi.get('name') or '').strip().lower()
                loc = poi.get('location') or poi.get('coordinates') or {}
                lat = loc.get('lat'); lng = loc.get('lng')
                if lat is None or lng is None:
                    return f"name:{name}"
                return f"name:{name}|geo:{round(float(lat), 6)},{round(float(lng), 6)}"

            def _existing_keys(itin: dict) -> set:
                keys = set()
                for day_list in (itin or {}).values():
                    if isinstance(day_list, list):
                        for p in day_list:
                            keys.add(_poi_key(p))
                return keys

            def _flatten_itinerary(itin: dict) -> list:
                flat = []
                for day_list in (itin or {}).values():
                    if isinstance(day_list, list):
                        flat.extend(day_list)
                return flat

            # 1) Load itinerary doc
            doc_ref = db_instance.collection('users').document(user_uid) \
                .collection('itineraries').document(itinerary_id)
            snap = doc_ref.get()
            if not snap.exists:
                return jsonify({"error": "Itinerary not found for this user."}), 404

            doc = snap.to_dict() or {}
            itinerary = doc.get('itinerary', {}) or {}
            if not isinstance(itinerary, dict) or not itinerary:
                return jsonify({"error": "Invalid itinerary structure."}), 400

            # 2) Compute required and current counts
            day_keys = [k for k in itinerary.keys() if isinstance(k, str) and k.lower().startswith('day ')]
            num_days = len(day_keys) if day_keys else 1
            # prefer stored meta.max_per_day if present; fallback to builder default 2
            max_per_day = (doc.get('meta', {}) or {}).get('max_per_day') or 2
            required_total = int(num_days) * int(max_per_day)

            current_flat = _flatten_itinerary(itinerary)
            current_count = len(current_flat)
            missing = required_total - current_count

            if missing <= 0:
                return jsonify({
                    'message': 'No replenishment needed',
                    'itinerary_id': itinerary_id,
                    'required_total': required_total,
                    'current_count': current_count,
                    'added': 0,
                    'missing_after': 0,
                    'itinerary': itinerary
                }), 200

            # 3) Build preferences for fetching candidates (best effort based on stored fields)
            location = doc.get('location') or doc.get('city')
            if not location:
                return jsonify({"error": "Cannot determine location for itinerary."}), 400

            user_input = {
                'location': location,
                # Leave filters broad; generator will score/shape them later
                'selected_interests': (doc.get('preferences', {}) or {}).get('selected_interests', []),
                'budget': (doc.get('preferences', {}) or {}).get('budget', 'unknown'),
                'with_pets': (doc.get('preferences', {}) or {}).get('with_pets', False),
                'with_disabilities': (doc.get('preferences', {}) or {}).get('with_disabilities', False),
            }

            # 4) Fetch candidate POIs and dedupe
            candidates = get_filtered_pois(user_input) or []
            # Limit scan to reduce CPU if huge
            cap = max(missing * limit_factor, missing)
            candidates = candidates[: max(cap, 0)]

            existing_keys = _existing_keys(itinerary)
            picked = []
            picked_keys = set()

            # Map candidates into itinerary activity shape (mirror generate_itinerary)
            from Itinerarybuilder.itinerary_builder import TAG_TO_BEST_TIME

            def _activity_from_candidate(poi: dict) -> dict:
                best_time = poi.get('best_time') or 'Anytime'
                if best_time == 'Anytime':
                    for tag in poi.get('tags', []) or []:
                        if tag in TAG_TO_BEST_TIME:
                            best_time = TAG_TO_BEST_TIME[tag]
                            break
                return {
                    'name': poi.get('name', ''),
                    'tags': poi.get('tags', []) or [],
                    'best_time': best_time,
                    'budget_category': poi.get('budget_category', 'unknown'),
                    'disclaimer': poi.get('disclaimer', ''),
                    'photo_url': poi.get('photo_url', ''),
                    'coordinates': poi.get('coordinates', {})
                }

            for poi in candidates:
                key = _poi_key(poi)
                if key in existing_keys or key in picked_keys:
                    continue
                picked.append(_activity_from_candidate(poi))
                picked_keys.add(key)
                if len(picked) >= missing:
                    break

            added = len(picked)
            if added == 0:
                return jsonify({
                    'message': 'No suitable new POIs found for replenishment',
                    'itinerary_id': itinerary_id,
                    'required_total': required_total,
                    'previous_count': current_count,
                    'added': 0,
                    'current_count': current_count,
                    'missing_after': required_total - current_count,
                    'itinerary': itinerary
                }), 206

            if dry_run:
                return jsonify({
                    'message': 'Dry run: POIs would be replenished',
                    'itinerary_id': itinerary_id,
                    'required_total': required_total,
                    'previous_count': current_count,
                    'added': added,
                    'current_count': current_count + added,
                    'missing_after': max(0, required_total - (current_count + added)),
                    'preview_added': picked,
                    'itinerary': itinerary
                }), 200

            # 5) Append picked items into itinerary (temporary; optimizer will redistribute by proximity)
            # Append to Day 1 list to ensure optimizer picks them up
            day1_key = day_keys[0] if day_keys else 'Day 1'
            itinerary.setdefault(day1_key, [])
            itinerary[day1_key].extend(picked)

            # 6) Persist and optimize
            new_count = current_count + added
            poi_count = sum(len(day) for day in itinerary.values())
            doc_ref.update({
                'itinerary': itinerary,
                'poi_count': poi_count,
                'updated_at': firestore.SERVER_TIMESTAMP
            })

            # Import optimizer locally to avoid circular imports
            try:
                from diary.services.proximity_optimizer import optimize_itinerary_by_proximity
                optimize_itinerary_by_proximity(user_uid, itinerary_id)
            except Exception as e:
                current_app.logger.error(f"Optimizer failed for {itinerary_id}: {e}")
                # Proceed without failing request; return non-optimized but updated itinerary

            # Re-read after optimization (if succeeded)
            snap2 = doc_ref.get()
            final_doc = snap2.to_dict() or {}
            final_itin = final_doc.get('itinerary', itinerary)
            final_count = sum(len(day) for day in (final_itin or {}).values())

            status_msg = 'Itinerary replenished and re-optimized' if final_itin != itinerary else 'Itinerary replenished (no optimization applied)'
            partial = final_count < required_total

            return jsonify({
                'message': ('Partial replenish: not enough unique POIs available' if partial else status_msg),
                'itinerary_id': itinerary_id,
                'required_total': required_total,
                'previous_count': current_count,
                'added': added,
                'current_count': final_count,
                'missing_after': max(0, required_total - final_count),
                'itinerary': final_itin
            }), 200

        except Exception as e:
            current_app.logger.error(f"Replenish failed for itinerary {itinerary_id}: {e}", exc_info=True)
            return jsonify({'error': 'Failed to replenish itinerary.', 'details': str(e)}), 500

    @itinerary_bp.route("/search-place", methods=["POST"])
    def search_place():
        """
        Search for POIs to manually replenish an itinerary.
        Priority:
        1. Firestore places/{location}/poi_list
        2. Google Places API (normalized + stored)
        3. hidden_gems/{location}/poi_list
        Returns ranked raw JSON results.
        """
        data = request.get_json()
        user_id = data.get("user_id")
        itinerary_id = data.get("itinerary_id")
        query = data.get("query")

        if not user_id or not itinerary_id or not query:
            return jsonify({"error": "user_id, itinerary_id, and query are required"}), 400

        # 1. Fetch itinerary to infer location
        itinerary_ref = db_instance.collection("users").document(user_id).collection("itineraries").document(itinerary_id)
        itinerary_doc = itinerary_ref.get()
        if not itinerary_doc.exists:
            return jsonify({"error": "Itinerary not found"}), 404

        location = itinerary_doc.to_dict().get("location")
        if not location:
            return jsonify({"error": "Itinerary missing location"}), 400

        results = []

        # 2. Use NLP to detect category vs. specific place
        query_type = suggestion_utils.classify_query(query)

        # 3. Check Firestore POIs
        firestore_pois = get_places_for_location(db_instance, location, query, query_type)
        for poi in firestore_pois:
            poi["source"] = "firestore"
        results.extend(firestore_pois)

        # 4. If not enough, call Google Places
        if len(results) < 5:
            google_places = fetch_places_from_google(query, location)
            normalized = [
                normalization_utils.normalize_place(place, location) for place in google_places
            ]
            # Persist to Firestore
            for poi in normalized:
                db_instance.collection("places").document(location).collection("poi_list").document(poi["place_id"]).set(poi)
                poi["source"] = "google_places"
            results.extend(normalized)

        # 5. If still not enough, fallback to hidden gems
        if len(results) < 5:
            hidden_gems_ref = db_instance.collection("hidden_gems").document(location).collection("poi_list")
            hidden_gems = [doc.to_dict() for doc in hidden_gems_ref.stream()]
            for poi in hidden_gems:
                poi["source"] = "hidden_gems"
                poi["is_hidden_gem"] = True
            results.extend(hidden_gems)

        # 6. Rank and return
        ranked_results = ranking_utils.rank_pois(results)

        return jsonify(ranked_results), 200
    
    @itinerary_bp.route("/places/autocomplete", methods=["POST"])
    @login_required_user
    def places_autocomplete():
        """
        Provides search-as-you-type suggestions for places.
        Body: { "query": "Lalbagh", "location": "Bengaluru" }
        """
        data = request.get_json()
        query = data.get("query")
        location = data.get("location")

        if not query or not location:
            return jsonify({"error": "query and location are required"}), 400

        try:
            api_key = load_google_api_key()
            suggestions = search_places_autocomplete(query, location, api_key)
            return jsonify(suggestions), 200
        except Exception as e:
            current_app.logger.error(f"Autocomplete failed: {e}")
            return jsonify({"error": "Failed to fetch suggestions."}), 500


    @itinerary_bp.route("/places/details/<place_id>", methods=["GET"])
    @login_required_user
    def get_place_details_by_id(place_id):
        """
        Gets the full, normalized details for a place.
        Implements a "cache-first" strategy using the nested '/places/{location}/poi_list' collection.
        """
        # 1. Get the required 'location' from the URL's query parameter
        location = request.args.get('location')
        if not location:
            return jsonify({"error": "A 'location' query parameter is required."}), 400
        
        # Sanitize the location name for use as a document ID (e.g., lowercase)
        location_id = location.lower()

        try:
            # 2. Build the path to the document in your existing Firestore structure
            cache_ref = db_instance.collection('places').document(location_id) \
                .collection('poi_list').document(place_id)

            # 3. Check your database first (the cache)
            cached_doc = cache_ref.get()
            if cached_doc.exists:
                current_app.logger.info(f"CACHE HIT for place_id: {place_id} in location: {location_id}")
                return jsonify(cached_doc.to_dict()), 200

            # 4. If not in your cache, call the Google API (Cache Miss)
            current_app.logger.info(f"CACHE MISS for place_id: {place_id}. Fetching from Google.")
            api_key = load_google_api_key()
            details = get_place_details(place_id, api_key)

            # 5. Save the new details back to your cache for next time
            cache_ref.set(details)
            
            return jsonify(details), 200

        except Exception as e:
            current_app.logger.error(f"Place details failed for {place_id}: {e}")
            return jsonify({"error": "Failed to fetch place details."}), 500
    
    return itinerary_bp