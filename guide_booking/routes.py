# guide_booking/routes.py
from flask import Blueprint, request, jsonify, session, current_app
from firebase_admin import firestore
from user_auth.utils import login_required_user
import datetime
import uuid

def create_guide_booking_bp(db_instance):
    guide_booking_bp = Blueprint('guide_booking_bp', __name__, url_prefix='/guides')

    @guide_booking_bp.route('/', methods=['GET'])
    @login_required_user
    def list_guides():
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required."}), 401

        location_filter = request.args.get('location')
        language_filter = request.args.get('language')
        tier_filter = request.args.get('tier')

        guides_query = db_instance.collection('guides').where('status', '==', 'approved')

        if location_filter:
            guides_query = guides_query.where('regions_covered', 'array_contains', location_filter.title())
        if language_filter:
            guides_query = guides_query.where('languages_spoken', 'array_contains', language_filter.title())
        if tier_filter and tier_filter in ['low', 'mid', 'high']:
            guides_query = guides_query.where('tier', '==', tier_filter)

        guides_query = guides_query.order_by('average_rating', direction=firestore.Query.DESCENDING)

        try:
            guides_docs = guides_query.stream()
            guides_list = []
            for doc in guides_docs:
                guide_data = doc.to_dict()
                guides_list.append({
                    "id": doc.id,
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
            guides_list.sort(key=lambda x: x.get('average_rating', 0), reverse=True)
            return jsonify({"message": "Guides retrieved successfully", "guides": guides_list}), 200
        except Exception as e:
            current_app.logger.error(f"Error listing guides for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve guides."}), 500

    def score_guide(guide_data, booking_criteria):
        score = 0
        score += guide_data.get('average_rating', 0) * 20
        score += guide_data.get('total_tours_completed', 0) / 10

        requested_languages = set(booking_criteria.get('languages_needed', []))
        guide_languages = set(guide_data.get('languages_spoken', []))
        if requested_languages:
            score += len(requested_languages.intersection(guide_languages)) * 5

        requested_specialties = set(booking_criteria.get('specialties_needed', []))
        guide_specialties = set(guide_data.get('specialties', []))
        if requested_specialties:
            score += len(requested_specialties.intersection(guide_specialties)) * 5

        return score

    @guide_booking_bp.route('/request-assignment', methods=['POST'])
    @login_required_user
    def request_guide_assignment():
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required."}), 401

        data = request.get_json()
        itinerary_id = data.get('itinerary_id')
        requested_location = data.get('location')
        segments = data.get('segments', [])

        if not itinerary_id and not requested_location:
            return jsonify({"error": "Missing required field: itinerary_id or location."}), 400

        try:
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
                    booking_criteria.update({
                        'start_date': itinerary_data.get('start_date'),
                        'end_date': itinerary_data.get('end_date'),
                        'location': itinerary_data.get('location'),
                        'specialties_needed': list({tag for day in itinerary_data.get('itinerary', {}).values() for poi in day for tag in poi.get('tags', []) if not segments or any(s.get('poi_name') == poi.get('name') for s in segments)}),
                        'languages_needed': ["English", "Hindi"]
                    })
                else:
                    return jsonify({"error": "Itinerary not found for this user."}), 404

            if not all(booking_criteria.get(k) for k in ['location', 'start_date', 'end_date']):
                return jsonify({"error": "Booking criteria could not be inferred. Please provide location and dates."}), 400

            start_date = datetime.datetime.fromisoformat(booking_criteria['start_date'].replace('Z', '+00:00'))
            if (start_date - datetime.datetime.now(datetime.timezone.utc)).total_seconds() < 48 * 3600:
                return jsonify({"error": "Booking is not allowed within 48 hours of the trip start time."}), 400

            eligible_guides_query = db_instance.collection('guides').where('status', '==', 'approved').where('regions_covered', 'array_contains', booking_criteria['location'].title())
            if booking_criteria['tier_preferred'] != 'any':
                eligible_guides_query = eligible_guides_query.where('tier', '==', booking_criteria['tier_preferred'])

            eligible_guide_candidates = list(eligible_guides_query.stream())
            
            available_guides = []
            if eligible_guide_candidates:
                conflicting_bookings_query = db_instance.collection('bookings').where('assigned_guide_uid', 'in', [doc.id for doc in eligible_guide_candidates]).where('status', 'in', ['pending_acceptance', 'accepted']).where('end_date', '>=', booking_criteria['start_date']).where('start_date', '<=', booking_criteria['end_date'])
                booked_guide_uids = {doc.to_dict()['assigned_guide_uid'] for doc in conflicting_bookings_query.stream()}
                available_guides = [doc for doc in eligible_guide_candidates if doc.id not in booked_guide_uids]

            if not available_guides:
                return jsonify({"message": "No available guides found matching your criteria for the requested dates."}), 404

            scored_guides = sorted(
                [{'id': doc.id, 'data': doc.to_dict(), 'score': score_guide(doc.to_dict(), booking_criteria)} for doc in available_guides],
                key=lambda x: x['score'], reverse=True
            )

            potential_guide_uids = [guide['id'] for guide in scored_guides]

            booking_id = str(uuid.uuid4())
            booking_data = {
                "booking_id": booking_id,
                "tourist_uid": user_uid,
                "itinerary_id": itinerary_id,
                "start_date": booking_criteria.get('start_date'),
                "end_date": booking_criteria.get('end_date'),
                "request_timestamp": firestore.SERVER_TIMESTAMP,
                "status": "pending_assignment",
                "potential_guides": potential_guide_uids,
                "assigned_guide_uid": None,
                "assignment_history": [],
                "message_to_guide": data.get('message_to_guide', "")
            }
            db_instance.collection('bookings').document(booking_id).set(booking_data)

            if itinerary_id:
                itinerary_ref.update({"booking_id": booking_id, "guide_booked_uid": None, "status": "pending_assignment"})

            return jsonify({
                "message": "Your request for a guide has been submitted and is being processed.",
                "booking_id": booking_id,
            }), 201

        except Exception as e:
            current_app.logger.error(f"Error processing assignment request for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to assign a guide.", "details": str(e)}), 500

    @guide_booking_bp.route('/my-bookings', methods=['GET'])
    @login_required_user
    def get_my_bookings():
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required."}), 401
        try:
            bookings_docs = db_instance.collection('bookings').where('tourist_uid', '==', user_uid).stream()
            my_bookings = []
            for doc in bookings_docs:
                booking_data = doc.to_dict()
                if booking_data.get('assigned_guide_uid'):
                    guide_doc = db_instance.collection('guides').document(booking_data['assigned_guide_uid']).get()
                    if guide_doc.exists:
                        booking_data['assigned_guide_name'] = guide_doc.to_dict().get('name')
                my_bookings.append(booking_data)
            my_bookings.sort(key=lambda x: x.get('request_timestamp'), reverse=True)
            return jsonify({"message": "My bookings retrieved successfully", "bookings": my_bookings}), 200
        except Exception as e:
            current_app.logger.error(f"Error retrieving bookings for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve your bookings."}), 500

    @guide_booking_bp.route('/<booking_id>/cancel', methods=['POST'])
    @login_required_user
    def cancel_booking(booking_id):
        # This endpoint is for the TOURIST to cancel.
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required."}), 401
        
        data = request.get_json()
        cancellation_reason = data.get('reason')
        if not cancellation_reason:
            return jsonify({"error": "A reason for cancellation is required."}), 400

        booking_ref = db_instance.collection('bookings').document(booking_id)
        booking_doc = booking_ref.get()

        if not booking_doc.exists:
            return jsonify({"error": "Booking not found."}), 404

        booking_data = booking_doc.to_dict()
        if booking_data.get('tourist_uid') != user_uid:
            return jsonify({"error": "You are not authorized to cancel this booking."}), 403

        if booking_data.get('status') not in ['pending_acceptance', 'accepted', 'pending_assignment']:
            return jsonify({"message": f"This booking cannot be cancelled as it is already {booking_data.get('status')}."}), 400
        
        try:
            booking_ref.update({
                "status": "cancelled_by_tourist",
                "cancellation_reason": cancellation_reason,
            })
            return jsonify({"message": "Booking cancelled successfully."}), 200
        except Exception as e:
            current_app.logger.error(f"Error cancelling booking {booking_id}: {e}", exc_info=True)
            return jsonify({"error": "Failed to cancel the booking."}), 500

    @guide_booking_bp.route('/<guide_id>/review', methods=['POST'])
    @login_required_user
    def submit_guide_review(guide_id):
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required."}), 401
        
        data = request.get_json()
        rating = data.get('rating')
        comment = data.get('comment', "")

        if not isinstance(rating, (int, float)) or not (1 <= rating <= 5):
            return jsonify({"error": "A valid rating between 1 and 5 is required."}), 400

        try:
            guide_ref = db_instance.collection('guides').document(guide_id)
            if not guide_ref.get().exists:
                return jsonify({"error": "Guide not found."}), 404
            
            review_id = str(uuid.uuid4())
            review_data = {
                "review_id": review_id,
                "tourist_uid": user_uid,
                "guide_uid": guide_id,
                "rating": rating,
                "comment": comment,
                "timestamp": firestore.SERVER_TIMESTAMP
            }
            db_instance.collection('guides').document(guide_id).collection('reviews').document(review_id).set(review_data)
            
            current_app.logger.info(f"Review {review_id} submitted for guide {guide_id}. The average rating will be updated automatically.")

            return jsonify({"message": "Review submitted successfully!", "review_id": review_id}), 201
        except Exception as e:
            current_app.logger.error(f"Error submitting review for guide {guide_id}: {e}", exc_info=True)
            return jsonify({"error": "Failed to submit review."}), 500
    
    # **[NEW] Endpoint for guide to ACCEPT a booking**
    @guide_booking_bp.route('/bookings/<booking_id>/accept', methods=['POST'])
    @login_required_user # We assume the guide is also a logged-in user
    def accept_booking(booking_id):
        guide_uid = session.get('user_uid') # This is the guide's UID
        if not guide_uid:
            return jsonify({"error": "Authentication required."}), 401

        booking_ref = db_instance.collection('bookings').document(booking_id)
        booking_doc = booking_ref.get()

        if not booking_doc.exists:
            return jsonify({"error": "Booking not found."}), 404
        
        booking_data = booking_doc.to_dict()

        # Security Check: Only the assigned guide can accept
        if booking_data.get('assigned_guide_uid') != guide_uid:
            return jsonify({"error": "You are not authorized to accept this booking."}), 403

        # State Check: Can only accept if pending
        if booking_data.get('status') != 'pending_acceptance':
            return jsonify({"error": f"Booking is no longer pending acceptance. Current status: {booking_data.get('status')}"}), 400

        try:
            # Update booking status
            booking_ref.update({"status": "accepted"})
            
            # Update the corresponding itinerary
            tourist_uid = booking_data.get("tourist_uid")
            itinerary_id = booking_data.get("itinerary_id")
            if tourist_uid and itinerary_id:
                itinerary_ref = db_instance.collection('users').document(tourist_uid).collection('itineraries').document(itinerary_id)
                itinerary_ref.update({"guide_booked_uid": guide_uid, "status": "guide_confirmed"})

            # TODO: Send notification to tourist that the guide has accepted
            print(f"NOTIFICATION: Sent to tourist {tourist_uid} that booking {booking_id} was accepted by guide {guide_uid}.")

            return jsonify({"message": "Booking accepted successfully."}), 200
        except Exception as e:
            current_app.logger.error(f"Error accepting booking {booking_id} by guide {guide_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to accept booking."}), 500

    # **[NEW] Endpoint for guide to REJECT a booking**
    @guide_booking_bp.route('/bookings/<booking_id>/reject', methods=['POST'])
    @login_required_user # Guide must be logged in
    def reject_booking(booking_id):
        guide_uid = session.get('user_uid')
        if not guide_uid:
            return jsonify({"error": "Authentication required."}), 401

        data = request.get_json()
        reason = data.get('reason', 'No reason provided')

        booking_ref = db_instance.collection('bookings').document(booking_id)
        booking_doc = booking_ref.get()

        if not booking_doc.exists:
            return jsonify({"error": "Booking not found."}), 404

        booking_data = booking_doc.to_dict()

        if booking_data.get('assigned_guide_uid') != guide_uid:
            return jsonify({"error": "You are not authorized to reject this booking."}), 403
        
        if booking_data.get('status') != 'pending_acceptance':
            return jsonify({"error": f"Booking is no longer pending acceptance. Current status: {booking_data.get('status')}"}), 400

        try:
            # This status change will trigger the re-assignment Cloud Function
            booking_ref.update({
                "status": "rejected_by_guide",
                "rejection_reason": reason
            })

            # TODO: Send notification to tourist that the guide rejected
            print(f"NOTIFICATION: Informing system that guide {guide_uid} rejected booking {booking_id}.")

            return jsonify({"message": "Booking rejected successfully."}), 200
        except Exception as e:
            current_app.logger.error(f"Error rejecting booking {booking_id} by guide {guide_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to reject booking."}), 500

    return guide_booking_bp