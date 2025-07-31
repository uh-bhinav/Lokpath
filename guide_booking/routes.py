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
    
    @guide_booking_bp.route('/request_booking', methods=['POST'])
    @login_required_user # Only logged-in tourists can request bookings
    def request_guide_booking():
        user_uid = session.get('user_uid') # This is the tourist's UID
        if not user_uid:
            return jsonify({"error": "Authentication required to request a guide."}), 401

        data = request.get_json()

        # Input fields for guide request criteria
        requested_location = data.get('location') # e.g., "Bengaluru"
        requested_languages = data.get('languages_needed', []) # e.g., ["English", "Kannada"]
        requested_specialties = data.get('specialties_needed', []) # e.g., ["History", "Food"]
        requested_tier = data.get('tier_preferred') # e.g., "mid", "low", "high"

        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        message_to_guide = data.get('message_to_guide', "")
        itinerary_id = data.get('itinerary_id') # Optional: Link to a specific itinerary

        # --- Input Validation ---
        if not all([requested_location, requested_languages, start_date_str, end_date_str]):
            return jsonify({"error": "Missing required fields: location, languages_needed, start_date, end_date."}), 400
        if not isinstance(requested_languages, list) or not all(isinstance(x, str) for x in requested_languages):
            return jsonify({"error": "languages_needed must be a list of strings."}), 400
        if not isinstance(requested_specialties, list) or not all(isinstance(x, str) for x in requested_specialties):
            return jsonify({"error": "specialties_needed must be a list of strings."}), 400
        if requested_tier and requested_tier not in ['low', 'mid', 'high', 'any']:
            return jsonify({"error": "tier_preferred must be 'low', 'mid', 'high', or 'any'."}), 400

        try:
            # Parse dates
            start_date = datetime.datetime.fromisoformat(start_date_str.replace('Z', '+00:00')) # Handle 'Z' for UTC
            end_date = datetime.datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))     # Handle 'Z' for UTC
            if end_date < start_date:
                return jsonify({"error": "End date cannot be before start date."}), 400

            # --- Find eligible guides for this request ---
            # Step 1: Query Firestore with the maximum allowed filters (one array_contains/any)
            # Prioritize 'regions_covered' as it's geographic.
            eligible_guides_query = db_instance.collection('guides').where('status', '==', 'approved')

            # Apply regions_covered filter in Firestore
            eligible_guides_query = eligible_guides_query.where('regions_covered', 'array_contains', requested_location.title())

            # Apply tier filter in Firestore (can be combined with array_contains)
            if requested_tier and requested_tier != 'any':
                eligible_guides_query = eligible_guides_query.where('tier', '==', requested_tier)

            # Fetch candidates from Firestore
            eligible_guide_candidates = []
            for doc in eligible_guides_query.stream():
                guide_data = doc.to_dict()
                guide_data['id'] = doc.id # Add ID to dict for easier Python filtering
                eligible_guide_candidates.append(guide_data)

            # Step 2: Filter remaining array fields (languages, specialties) in Python
            final_eligible_guides_data = []
            requested_languages_set = set(l.title() for l in requested_languages) # Normalize and convert to set for efficiency
            requested_specialties_set = set(s.title() for s in requested_specialties) # Normalize and convert to set

            for guide_data in eligible_guide_candidates:
                guide_languages = set(guide_data.get('languages_spoken', []))
                guide_specialties = set(guide_data.get('specialties', []))

                # Check if guide speaks ALL requested languages (intersection)
                if requested_languages_set and not guide_languages.issuperset(requested_languages_set):
                    continue # Skip if guide doesn't speak all required languages

                # Check if guide has ALL requested specialties (intersection)
                if requested_specialties_set and not guide_specialties.issuperset(requested_specialties_set):
                    continue # Skip if guide doesn't have all required specialties

                final_eligible_guides_data.append(guide_data)

            eligible_guide_uids = [guide['id'] for guide in final_eligible_guides_data] # Get UIDs from filtered data

            if not eligible_guide_uids:
                current_app.logger.info(f"No eligible guides found for request by {user_uid} for {requested_location} after in-Python filtering.")
                return jsonify({"message": "No guides found matching your criteria. Please adjust your request."}), 404

            # --- Store the Booking Request ---
            booking_id = str(uuid.uuid4())
            booking_data = {
                "booking_id": booking_id, # Redundant but useful for client
                "tourist_uid": user_uid,
                "requested_location": requested_location,
                "requested_languages": requested_languages,
                "requested_specialties": requested_specialties,
                "requested_tier": requested_tier,
                "request_timestamp": firestore.SERVER_TIMESTAMP,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "message_to_guide": message_to_guide,
                "itinerary_id": itinerary_id, # Will be null if not provided
                "status": "pending_acceptance", # Initial status
                "assigned_guide_uid": None, # Will be filled when a guide accepts (by separate guide platform)
                "potential_guide_uids": eligible_guide_uids, # List of guides who might see this request
                "cancellation_history": { # To track cancellations for this specific booking
                    "tourist_cancelled": False,
                    "guide_cancelled": False,
                    "reason": None
                }
            }

            db_instance.collection('bookings').document(booking_id).set(booking_data)
            current_app.logger.info(f"Booking request {booking_id} created by user {user_uid}. Eligible guides: {len(eligible_guide_uids)}")

            return jsonify({
                "message": "Guide booking request submitted successfully! Guides are being notified.",
                "booking_id": booking_id,
                "eligible_guides_count": len(eligible_guide_uids)
            }), 201

        except ValueError:
            return jsonify({"error": "Invalid date format. Use ISO 8601 (YYYY-MM-DDTHH:MM:SS.sssZ) for start_date/end_date."}), 400
        except Exception as e:
            current_app.logger.error(f"Error submitting booking request for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to submit booking request.", "details": str(e)}), 500
    
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