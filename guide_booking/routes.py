# guide_booking/routes.py
from flask import Blueprint, request, jsonify, session, current_app
from firebase_admin import firestore
from user_auth.utils import login_required_user # Tourists need to be logged in to browse guides
import datetime 
import uuid 



def create_guide_booking_bp(db_instance):
    guide_booking_bp = Blueprint('guide_booking_bp', __name__, url_prefix='/guides')

    @guide_booking_bp.route('/', methods=['GET'])
    @login_required_user # Only logged-in tourists can browse guides
    def list_guides():
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required."}), 401

        # Get query parameters for filtering (e.g., location, language, tier)
        location_filter = request.args.get('location')
        language_filter = request.args.get('language')
        tier_filter = request.args.get('tier') # low, mid, high

        guides_query = db_instance.collection('guides').where('status', '==', 'approved') # Only list approved guides

        # Apply filters if provided
        if location_filter:
            # Assuming 'regions_covered' is an array in Firestore
            # For array contains, you need array-contains-any or array-contains (exact match)
            guides_query = guides_query.where('regions_covered', 'array_contains', location_filter.title())

        if language_filter:
            guides_query = guides_query.where('languages_spoken', 'array_contains', language_filter.title())

        if tier_filter and tier_filter in ['low', 'mid', 'high']:
            guides_query = guides_query.where('tier', '==', tier_filter)

        # Ordering (e.g., by rating, but Firestore requires indexing for multiple orderings/filters)
        # For simplicity, we'll just get results and sort in Python or rely on default Firestore order
        guides_query = guides_query.order_by('average_rating', direction=firestore.Query.DESCENDING)

        try:
            guides_docs = guides_query.stream()
            guides_list = []
            for doc in guides_docs:
                guide_data = doc.to_dict()
                # You might want to filter sensitive data here before sending to client
                # e.g., remove actual email/phone if not public
                guides_list.append({
                    "id": doc.id, # The UID from Firebase Authentication
                    "name": guide_data.get('name'),
                    "bio": guide_data.get('bio'),
                    "languages_spoken": guide_data.get('languages_spoken'),
                    "specialties": guide_data.get('specialties'),
                    "regions_covered": guide_data.get('regions_covered'),
                    "tier": guide_data.get('tier'),
                    "average_rating": guide_data.get('average_rating'),
                    "total_tours_completed": guide_data.get('total_tours_completed'),
                    "profile_image_url": guide_data.get('profile_image_url')
                })

            # Manual sorting if Firestore query ordering isn't sufficient
            guides_list.sort(key=lambda x: x.get('average_rating', 0), reverse=True)


            return jsonify({"message": "Guides retrieved successfully", "guides": guides_list}), 200
        except Exception as e:
            current_app.logger.error(f"Error listing guides for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve guides."}), 500

    # Future endpoints for booking requests, reviews, etc. will go here

    def score_guide(guide_data, booking_criteria):
        """Calculates a match score for a guide based on booking criteria."""
        score = 0

        # Factor 1: Average Rating (High priority)
        # Weighting 1 to 5 stars is a good start.
        score += guide_data.get('average_rating', 0) * 20 # 20 points per star

        # Factor 2: Total Tours Completed (Experience)
        # Add points for experience
        score += guide_data.get('total_tours_completed', 0) / 10 # 1 point per 10 tours

        # Factor 3: Matching more languages (Bonus)
        requested_languages = set(booking_criteria.get('languages_needed', []))
        guide_languages = set(guide_data.get('languages_spoken', []))
        if requested_languages:
            score += len(requested_languages.intersection(guide_languages)) * 5 # 5 points per matched language

        # Factor 4: Matching more specialties (Bonus)
        requested_specialties = set(booking_criteria.get('specialties_needed', []))
        guide_specialties = set(guide_data.get('specialties', []))
        if requested_specialties:
            score += len(requested_specialties.intersection(guide_specialties)) * 5 # 5 points per matched specialty

        # Add other scoring factors here in the future

        return score
    
    @guide_booking_bp.route('/request-assignment', methods=['POST'])
    @login_required_user
    def request_guide_assignment():
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required."}), 401

        data = request.get_json()
        
        # Determine if the request is from an itinerary or a direct request
        itinerary_id = data.get('itinerary_id')
        requested_location = data.get('location')
        segments = data.get('segments', [])
        
        if not itinerary_id and not requested_location:
            return jsonify({"error": "Missing required field: itinerary_id or location."}), 400

        try:
            # --- Get the user's booking criteria ---
            booking_criteria = {
                "location": requested_location,
                "languages_needed": data.get('languages_needed', []),
                "specialties_needed": data.get('specialties_needed', []),
                "tier_preferred": data.get('tier_preferred', 'any'),
                "start_date": data.get('start_date'),
                "end_date": data.get('end_date'),
                "itinerary_id": itinerary_id,
            }

            if itinerary_id:
                itinerary_ref = db_instance.collection('users').document(user_uid).collection('itineraries').document(itinerary_id)
                itinerary_doc = itinerary_ref.get()
                if itinerary_doc.exists:
                    itinerary_data = itinerary_doc.to_dict()

                    # Fetch start/end dates and location from the itinerary
                    booking_criteria['start_date'] = itinerary_data.get('start_date')
                    booking_criteria['end_date'] = itinerary_data.get('end_date')
                    booking_criteria['location'] = itinerary_data.get('location')

                    # Automatically infer specialties and languages from all POI tags in the itinerary
                    all_poi_tags = set()
                    for day_plan in itinerary_data.get('itinerary', {}).values():
                        for poi in day_plan:
                            if not segments or any(s.get('poi_name') == poi.get('name') or s.get('poi_id') == poi.get('poi_id') for s in segments):
                                all_poi_tags.update(poi.get('tags', []))
                            

                    # Use these tags as the specialties needed
                    booking_criteria['specialties_needed'] = list(all_poi_tags)
                    # For languages, we can assume English and Hindi for now or infer from location.
                    # A good future improvement would be to store languages in itinerary itself.
                    booking_criteria['languages_needed'] = ["English", "Hindi"] 

                else:
                    return jsonify({"error": "Itinerary not found for this user."}), 404

            if not all([booking_criteria.get('location'), booking_criteria.get('start_date'), booking_criteria.get('end_date')]):
                return jsonify({"error": "Booking criteria could not be inferred from the itinerary. Please provide location and dates."}), 400

            # --- Find eligible guides for assignment ---
            eligible_guides_query = db_instance.collection('guides').where('status', '==', 'approved')

            eligible_guides_query = eligible_guides_query.where('regions_covered', 'array_contains', booking_criteria['location'].title())

            if booking_criteria['tier_preferred'] and booking_criteria['tier_preferred'] != 'any':
                eligible_guides_query = eligible_guides_query.where('tier', '==', booking_criteria['tier_preferred'])

            eligible_guide_candidates = [doc for doc in eligible_guides_query.stream()]
            print(f"DEBUG: Initial Firestore query found {len(eligible_guide_candidates)} eligible guides.") # <--- NEW DEBUGGING LINE


            final_eligible_guides = []
            requested_specialties_set = set(s.title() for s in booking_criteria['specialties_needed'])
            requested_languages_set = set(l.title() for l in booking_criteria['languages_needed'])

            for doc in eligible_guide_candidates:
                guide_data = doc.to_dict()
                guide_specialties = set(guide_data.get('specialties', []))
                guide_languages = set(guide_data.get('languages_spoken', []))

            # Filter in Python based on languages
                if requested_languages_set and not guide_languages.issuperset(requested_languages_set):
                    print(f"DEBUG: Guide {doc.id} filtered out for languages.")
                    continue

            # Filter in Python based on specialties
                if requested_specialties_set and not guide_specialties.issuperset(requested_specialties_set):
                    print(f"DEBUG: Guide {doc.id} filtered out for specialties.")
                    continue

                final_eligible_guides.append(doc)
                
            print(f"DEBUG: After Python filtering, found {len(final_eligible_guides)} guides.")

            # --- CRITICAL NEW LOGIC: Availability Check ---
            # 1. Get the list of all eligible guide UIDs
            eligible_guide_uids = [doc.id for doc in final_eligible_guides]
            if not eligible_guide_uids:
                return jsonify({"message": "No guides found matching your criteria. Please try again with different criteria."}), 404

            # 2. Check the 'bookings' collection for conflicts with the requested dates
            # This query finds guides who are already booked on the requested dates.
            conflicting_bookings_query = db_instance.collection('bookings') \
                .where('assigned_guide_uid', 'in', eligible_guide_uids) \
                .where('status', 'in', ['pending_acceptance', 'accepted']) \
                .where('end_date', '>=', booking_criteria['start_date']) \
                .where('start_date', '<=', booking_criteria['end_date'])

            booked_guide_uids = {doc.to_dict()['assigned_guide_uid'] for doc in conflicting_bookings_query.stream()}

            # 3. Filter out the booked guides from the eligible list
            truly_available_guides = [doc for doc in final_eligible_guides if doc.id not in booked_guide_uids]

            if not truly_available_guides:
                return jsonify({"message": "All eligible guides are currently booked for the requested dates. Please try another time."}), 404

            # --- Core "Ola/Uber" Assignment Logic ---
            if not final_eligible_guides:
                return jsonify({"message": "No guides found matching your criteria. Please try again with different criteria."}), 404
            
            scored_guides = []
            for doc in final_eligible_guides:
                guide_data = doc.to_dict()
                guide_id = doc.id
                match_score = score_guide(guide_data, booking_criteria)
                scored_guides.append({'id': guide_id, 'data': guide_data, 'score': match_score})

            # 2. Find the highest-scoring guide
            if not scored_guides:
                return jsonify({"message": "No guides could be scored for assignment."}), 500 # Should not happen, but for safety

            scored_guides.sort(key=lambda x: x['score'], reverse=True)
            assigned_guide_info = scored_guides[0] # Pick the top scoring guide

            assigned_guide_uid = assigned_guide_info['id']
            assigned_guide_details = assigned_guide_info['data']
            
            booking_id = str(uuid.uuid4())
            booking_data = {
                "booking_id": booking_id,
                "tourist_uid": user_uid,
                "assigned_guide_uid": assigned_guide_uid,
                "itinerary_id": itinerary_id,
                "start_date": booking_criteria.get('start_date'),
                "end_date": booking_criteria.get('end_date'),
                "request_timestamp": firestore.SERVER_TIMESTAMP,
                "status": "pending_acceptance",
                "message_to_guide": data.get('message_to_guide', ""),
                "cancellation_history": {
                    "tourist_cancelled": False,
                    "guide_cancelled": False,
                    "reason": None
                }
            }
            db_instance.collection('bookings').document(booking_id).set(booking_data)

            if itinerary_id:
                itinerary_ref.update({"booking_id": booking_id, "guide_booked_uid": assigned_guide_uid, "status": "pending_acceptance"})

            return jsonify({
                "message": "A guide has been assigned to your request.",
                "booking_id": booking_id,
                "assigned_guide": {
                    "id": assigned_guide_uid,
                    "name": assigned_guide_details.get('name'),
                    "profile_image_url": assigned_guide_details.get('profile_image_url'),
                    "bio": assigned_guide_details.get('bio'),
                    "average_rating": assigned_guide_details.get('average_rating'),
                    "tier": assigned_guide_details.get('tier'),
                }
            }), 201

        except Exception as e:
            current_app.logger.error(f"Error processing assignment request for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to assign a guide.", "details": str(e)}), 500

    
    @guide_booking_bp.route('/my-bookings', methods=['GET'])
    @login_required_user # Only logged-in tourists can view their bookings
    def get_my_bookings():
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required to view bookings."}), 401

        try:
            # Query bookings specific to this tourist
            # This query will likely require a single-field index on 'tourist_uid' in the 'bookings' collection.
            bookings_docs = db_instance.collection('bookings').where('tourist_uid', '==', user_uid).stream()

            my_bookings = []
            for doc in bookings_docs:
                booking_data = doc.to_dict()

                # Optionally fetch assigned guide's name for display
                assigned_guide_name = None
                if booking_data.get('assigned_guide_uid'):
                    try:
                        guide_doc = db_instance.collection('guides').document(booking_data['assigned_guide_uid']).get()
                        if guide_doc.exists:
                            assigned_guide_name = guide_doc.to_dict().get('name')
                    except Exception as e:
                        current_app.logger.error(f"Error fetching guide name for booking {doc.id}: {e}")
                booking_data['assigned_guide_name'] = assigned_guide_name

                my_bookings.append(booking_data)

            # Sort by request_timestamp descending (most recent first)
            my_bookings.sort(key=lambda x: x.get('request_timestamp', firestore.SERVER_TIMESTAMP), reverse=True)


            return jsonify({"message": "My bookings retrieved successfully", "bookings": my_bookings}), 200

        except Exception as e:
            current_app.logger.error(f"Error retrieving bookings for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve bookings."}), 500
    
    @guide_booking_bp.route('/<booking_id>/cancel', methods=['POST'])
    @login_required_user # Only logged-in tourists can cancel their bookings
    def cancel_booking(booking_id):
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required to cancel a booking."}), 401

        data = request.get_json()
        cancellation_reason = data.get('reason') # e.g., "changed_mind", "guide_unresponsive", "emergency"

        if not cancellation_reason:
            return jsonify({"error": "Cancellation reason is required."}), 400

        # You can define allowed reasons here for better data consistency:
        allowed_reasons = ["changed_mind", "guide_unresponsive", "scheduling_conflict", "emergency", "other"]
        if cancellation_reason not in allowed_reasons:
            return jsonify({"error": f"Invalid cancellation reason. Allowed: {', '.join(allowed_reasons)}"}), 400

        booking_ref = db_instance.collection('bookings').document(booking_id)
        booking_doc = booking_ref.get()

        if not booking_doc.exists:
            return jsonify({"error": "Booking not found."}), 404

        booking_data = booking_doc.to_dict()

        # Ensure only the requesting tourist can cancel THEIR booking
        if booking_data.get('tourist_uid') != user_uid:
            current_app.logger.warning(f"Unauthorized cancellation attempt: User {user_uid} tried to cancel booking {booking_id} of another user.")
            return jsonify({"error": "Unauthorized: You can only cancel your own bookings."}), 403

        # Only allow cancellation if the booking is 'pending' or 'accepted'
        if booking_data.get('status') not in ['pending_acceptance', 'accepted']: # Use pending_acceptance
            return jsonify({"message": f"Booking cannot be cancelled as it is already {booking_data.get('status')}."}), 400

        try:
            # Update booking status to cancelled
            update_data = {
                "status": "cancelled",
                "cancellation_history.tourist_cancelled": True, # Set to True
                "cancellation_history.guide_cancelled": False,   # Explicitly set to False
                "cancellation_history.reason": cancellation_reason, # Update reason inside map
                "cancellation_history.timestamp": firestore.SERVER_TIMESTAMP, 
                "cancellation_initiator": "tourist"
            }
            booking_ref.update(update_data)
            current_app.logger.info(f"Booking {booking_id} cancelled by tourist {user_uid} for reason: {cancellation_reason}.")

            # --- Penalty Logic (Conceptual for now) ---
            # Update tourist's profile with a cancellation flag/count
            user_profile_ref = db_instance.collection('users').document(user_uid)
            user_profile_ref.update({
                'cancellation_count': firestore.Increment(1), # Increments cancellation count
                'last_cancellation_reason': cancellation_reason,
                'last_cancellation_timestamp': firestore.SERVER_TIMESTAMP
            })
            current_app.logger.info(f"Tourist {user_uid} cancellation count incremented.")
            # The penalty logic (e.g., pay more money next time) would be implemented in a pricing
            # service or frontend that queries this cancellation_count from the user's profile.
            # --- END Penalty Logic ---

            # --- Future: Notify Guide (via separate platform's webhook/PubSub) ---
            # This Flask app would ideally trigger a notification to the Guide Platform
            # so the guide is aware of the cancellation.
            # --- END Future ---

            return jsonify({"message": "Booking cancelled successfully!", "booking_id": booking_id}), 200

        except Exception as e:
            current_app.logger.error(f"Error cancelling booking {booking_id} for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to cancel booking.", "details": str(e)}), 500
        

    @guide_booking_bp.route('/<guide_id>/review', methods=['POST'])
    @login_required_user # Only logged-in tourists can submit reviews
    def submit_guide_review(guide_id):
        user_uid = session.get('user_uid') # This is the tourist's UID
        if not user_uid:
            return jsonify({"error": "Authentication required to submit a review."}), 401

        data = request.get_json()
        rating = data.get('rating')
        comment = data.get('comment', "")

        if not guide_id or not isinstance(rating, (int, float)):
            return jsonify({"error": "Missing guide_id or rating."}), 400

        if not (1 <= rating <= 5): # Assuming a 1-5 star rating system
            return jsonify({"error": "Rating must be between 1 and 5."}), 400

        try:
            # 1. Verify guide exists
            guide_ref = db_instance.collection('guides').document(guide_id)
            guide_doc = guide_ref.get()
            if not guide_doc.exists:
                return jsonify({"error": "Guide not found."}), 404

            # 2. Store the new review in a subcollection
            review_id = str(uuid.uuid4())
            review_data = {
                "review_id": review_id, # Redundant but useful for client
                "tourist_uid": user_uid,
                "guide_uid": guide_id,
                "rating": rating,
                "comment": comment,
                "timestamp": firestore.SERVER_TIMESTAMP
            }
            # Add review to guides/<guide_id>/reviews subcollection
            db_instance.collection('guides').document(guide_id).collection('reviews').document(review_id).set(review_data)
            current_app.logger.info(f"Review {review_id} submitted by {user_uid} for guide {guide_id}.")

            # 3. Update guide's average_rating and total_reviews
            # Fetch existing reviews to recalculate average.
            # For very high volume reviews, this recalculation might be better done by a
            # Firebase Cloud Function triggered by new reviews, to avoid race conditions and
            # blocking the API response. But for now, direct recalculation is fine.
            all_reviews_docs = db_instance.collection('guides').document(guide_id).collection('reviews').stream()
            total_rating = 0
            num_reviews = 0
            for doc in all_reviews_docs:
                review = doc.to_dict()
                total_rating += review.get('rating', 0)
                num_reviews += 1

            new_average_rating = round(total_rating / num_reviews, 1) if num_reviews > 0 else 0.0

            # Update the guide's main document
            guide_ref.update({
                "average_rating": new_average_rating,
                "total_reviews": num_reviews # Add this field to your guide data structure
            })
            current_app.logger.info(f"Guide {guide_id} average rating updated to {new_average_rating} based on {num_reviews} reviews.")


            return jsonify({"message": "Review submitted successfully!", "review_id": review_id}), 201

        except Exception as e:
            current_app.logger.error(f"Error submitting review for guide {guide_id} by user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to submit review.", "details": str(e)}), 500

    return guide_booking_bp