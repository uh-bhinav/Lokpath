# guide_booking/routes.py
from flask import Blueprint, request, jsonify, session, current_app
from firebase_admin import firestore
from user_auth.utils import login_required_user # Tourists need to be logged in to browse guides

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

    return guide_booking_bp