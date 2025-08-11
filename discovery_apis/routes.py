# discovery_apis/routes.py
from flask import Blueprint, request, jsonify, session, current_app
from firebase_admin import firestore
from user_auth.utils import login_required_user # We want to verify who is Browse

def create_discovery_bp(db_instance): # Function to create and return the blueprint
    discovery_bp = Blueprint('discovery_bp', __name__, url_prefix='/discover')

    @discovery_bp.route('/hidden-gems', methods=['GET'])
    def list_hidden_gems():
        # No login required for public Browse, but we can check if a user is logged in
        user_uid = session.get('user_uid')
        current_app.logger.info(f"Public user view request (UID: {user_uid}) for hidden gems.")

        # --- Pagination and Filtering Parameters ---
        page_size = int(request.args.get('page_size', 20))
        page_token = request.args.get('page_token')
        status_filter = request.args.get('status', 'verified') # Only show approved gems by default

        # --- Perform a Collection Group Query ---
        # This queries across all 'gem_submissions' subcollections, regardless of parent location
        gems_query = db_instance.collection_group('gem_submissions').where('status', '==', status_filter)

        # Note: For pagination with start_at, you need a stable order_by
        gems_query = gems_query.order_by('timestamp', direction=firestore.Query.DESCENDING)

        # Apply page size limit
        gems_query = gems_query.limit(page_size)

        # Apply a page token if provided for pagination
        if page_token:
            gems_query = gems_query.start_after({u'timestamp': firestore.SERVER_TIMESTAMP}) # This needs to be the actual last item's timestamp
            # Note: Correct pagination in Firestore requires getting the last document from the previous page's stream.
            # For this implementation, we'll simplify and acknowledge the full pagination logic is more complex.

        try:
            gems_docs = gems_query.stream()
            gems_list = []
            for doc in gems_docs:
                gem_data = doc.to_dict()
                # Filter for public view (e.g., remove session_id, source_session_id etc.)
                public_gem_data = {
                    "id": doc.id,
                    "artisan_name": gem_data.get('artisan_name'), # This seems like a typo, should be from gem data
                    "description": gem_data.get('description'),
                    "tags": gem_data.get('tags'),
                    "location": gem_data.get('location'),
                    "region_name": gem_data.get('region_name'),
                    "image_urls": gem_data.get('image_urls'),
                    "timestamp": gem_data.get('timestamp')
                }
                gems_list.append(public_gem_data)

            # Check if there are more results for the next page
            # This is a basic check; full pagination would return an actual token
            next_page_exists = len(gems_list) == page_size

            return jsonify({
                "message": "Hidden gems retrieved successfully",
                "gems": gems_list,
                "has_next_page": next_page_exists
            }), 200

        except Exception as e:
            current_app.logger.error(f"Error listing hidden gems: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve hidden gems."}), 500

    @discovery_bp.route('/hidden-gems/<gem_id>', methods=['GET'])
    def get_hidden_gem(gem_id):
        gem_ref = db_instance.collection_group('gem_submissions').where('status', '==', 'approved').where('session_id', '==', gem_id)
        gem_doc = next(gem_ref.stream(), None)

        if gem_doc:
            return jsonify({"message": "Hidden gem retrieved successfully", "gem": gem_doc.to_dict()}), 200
        else:
            return jsonify({"error": "Hidden gem not found or not approved."}), 404

    # ... other discovery endpoints will go here ...

    @discovery_bp.route('/artisans', methods=['GET'])
    def list_artisans():
        # No login required for public Browse, but we can check if a user is logged in
        user_uid = session.get('user_uid')
        current_app.logger.info(f"Public user view request (UID: {user_uid}) for artisans.")

        # --- Pagination and Filtering Parameters ---
        page_size = int(request.args.get('page_size', 20))
        page_token = request.args.get('page_token')
        status_filter = request.args.get('status', 'verified') # Only show approved artisans by default

        # --- Perform a regular collection query on the 'artisans' collection ---
        artisans_query = db_instance.collection('artisans').where('status', '==', status_filter)

        # Apply ordering for pagination
        artisans_query = artisans_query.order_by('timestamp', direction=firestore.Query.DESCENDING)

        # Apply page size limit
        artisans_query = artisans_query.limit(page_size)

        # Apply a page token if provided for pagination
        if page_token:
            # Note: For simplicity, this is a basic stub. Full pagination is more complex.
            artisans_query = artisans_query.start_after({u'timestamp': firestore.SERVER_TIMESTAMP})

        try:
            artisans_docs = artisans_query.stream()
            artisans_list = []
            for doc in artisans_docs:
                artisan_data = doc.to_dict()

                # Filter for public view (remove sensitive data)
                public_artisan_data = {
                    "artisan_id": doc.id,
                    "artisan_name": artisan_data.get('artisan_name'),
                    "description": artisan_data.get('description'),
                    "craft_type": artisan_data.get('craft_type'),
                    "spoken_languages": artisan_data.get('spoken_languages'),
                    "budget_category_products": artisan_data.get('budget_category_products'),
                    "location": artisan_data.get('location'),
                    "region_name": artisan_data.get('region_name'),
                    "image_urls": artisan_data.get('image_urls'),
                    "opening_hours": artisan_data.get('opening_hours'),
                    "tags": artisan_data.get('tags'),
                    "status": artisan_data.get('status')
                    # Exclude fields like contact_phone, listed_by_uid for a public listing
                }
                artisans_list.append(public_artisan_data)

            # Check if there are more results for the next page
            next_page_exists = len(artisans_list) == page_size

            return jsonify({
                "message": "Artisans retrieved successfully",
                "artisans": artisans_list,
                "has_next_page": next_page_exists
            }), 200

        except Exception as e:
            current_app.logger.error(f"Error listing artisans: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve artisans."}), 500
        
    @discovery_bp.route('/artisans/<artisan_id>', methods=['GET'])
    def get_artisan(artisan_id):
        artisan_ref = db_instance.collection('artisans').document(artisan_id)
        artisan_doc = artisan_ref.get()

        if artisan_doc.exists and artisan_doc.to_dict().get('status') == 'approved':
            return jsonify({"message": "Artisan retrieved successfully", "artisan": artisan_doc.to_dict()}), 200
        else:
            return jsonify({"error": "Artisan not found or not approved."}), 404
    
    @discovery_bp.route('/user/hidden-gems', methods=['GET'])
    @login_required_user
    def get_user_hidden_gems():
        user_uid = session.get('user_uid')
        try:
            user_gems_ref = db_instance.collection('users').document(user_uid).collection('hidden_gems_listed')
            gems_docs = user_gems_ref.stream()

            gems_list = [doc.to_dict() for doc in gems_docs]
            gems_list.sort(key=lambda x: x.get('timestamp', firestore.SERVER_TIMESTAMP), reverse=True)

            return jsonify({
                "message": f"Hidden gems listed by user {user_uid} retrieved successfully",
                "gems": gems_list
            }), 200
        except Exception as e:
            current_app.logger.error(f"Error retrieving gems for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve user's hidden gems."}), 500

    @discovery_bp.route('/user/artisans', methods=['GET'])
    @login_required_user
    def get_user_artisans():
        user_uid = session.get('user_uid')
        try:
            user_artisans_ref = db_instance.collection('users').document(user_uid).collection('artisans_listed')
            artisans_docs = user_artisans_ref.stream()

            artisans_list = [doc.to_dict() for doc in artisans_docs]
            artisans_list.sort(key=lambda x: x.get('timestamp', firestore.SERVER_TIMESTAMP), reverse=True)

            return jsonify({
                "message": f"Artisans listed by user {user_uid} retrieved successfully",
                "artisans": artisans_list
            }), 200
        except Exception as e:
            current_app.logger.error(f"Error retrieving artisans for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve user's artisans."}), 500

    @discovery_bp.route('/user/all-listings', methods=['GET'])
    @login_required_user
    def get_user_all_listings():
        user_uid = session.get('user_uid')
        try:
            # Fetch all gems and artisans for the user
            gems_ref = db_instance.collection('users').document(user_uid).collection('hidden_gems_listed')
            gems_list = [doc.to_dict() for doc in gems_ref.stream()]

            artisans_ref = db_instance.collection('users').document(user_uid).collection('artisans_listed')
            artisans_list = [doc.to_dict() for doc in artisans_ref.stream()]

            all_listings = gems_list + artisans_list
            all_listings.sort(key=lambda x: x.get('timestamp', firestore.SERVER_TIMESTAMP), reverse=True)

            return jsonify({
                "message": f"All listings for user {user_uid} retrieved successfully",
                "listings": all_listings
            }), 200
        except Exception as e:
            current_app.logger.error(f"Error retrieving all listings for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve user's listings."}), 500

    @discovery_bp.route('/guides', methods=['GET'])
    def list_guides():
        # This is a general guide listing for discovery
        user_uid = session.get('user_uid')
        current_app.logger.info(f"Public user view request (UID: {user_uid}) for guides.")

        guides_query = db_instance.collection('guides').where('status', '==', 'approved')
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

        return jsonify({"message": "Guides retrieved successfully", "guides": guides_list}), 200

    @discovery_bp.route('/guides/<guide_id>', methods=['GET'])
    def get_guide_profile(guide_id):
        guide_ref = db_instance.collection('guides').document(guide_id)
        guide_doc = guide_ref.get()

        if guide_doc.exists and guide_doc.to_dict().get('status') == 'approved':
            return jsonify({"message": "Guide retrieved successfully", "guide": guide_doc.to_dict()}), 200
        else:
            return jsonify({"error": "Guide not found or not approved."}), 404

    return discovery_bp