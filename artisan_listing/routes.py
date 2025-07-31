# artisan_listing/routes.py
from flask import Blueprint, request, jsonify, session, current_app
from firebase_admin import firestore
from user_auth.utils import login_required_user # Tourists list artisans
from shared_globals import session_store, reverse_geocode, extract_simplified_region, extract_state_city_from_google 
import datetime
import re
import uuid # Ensure uuid is imported
# NEW: No need for os, shutil, re here anymore if app.py handles moving and validation
# from app import session_store, reverse_geocode, extract_simplified_region # Direct import for clarity

# For direct import of globals from app.py, you need to ensure app.py is loaded first
# Or, pass these as arguments to create_artisan_bp, similar to db_instance.
# For simplicity of keeping app.py cleaner, we'll stick to direct import for now,
# assuming `app` has been created and globals populated.
# Alternative: if you move `session_store`, etc. to a `shared_utils.py`, import from there.

from utils.moderation import is_description_safe
from utils.tags_extractor import extract_tags


def create_artisan_bp(db_instance): # Function to create and return the blueprint
    artisan_bp = Blueprint('artisan_bp', __name__, url_prefix='/artisan')

    @artisan_bp.route('/submit-details', methods=['POST'])
    @login_required_user # Only logged-in tourists can list artisans
    def submit_artisan_details():
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required to list an artisan."}), 401

        data = request.get_json()
        session_id = data.get('session_id')
        artisan_name = data.get('artisan_name')
        description = data.get('description')
        craft_type = data.get('craft_type')
        spoken_languages = data.get('spoken_languages', [])
        budget_category_products = data.get('budget_category_products')
        contact_phone = data.get('contact_phone')
        contact_email = data.get('contact_email')
        open_to_visits = data.get('open_to_visits')
        offers_workshops = data.get('offers_workshops')
        opening_hours = data.get('opening_hours') # <--- NEW: Get opening_hours

        if not session_id or not artisan_name or not description or not craft_type or not budget_category_products:
            return jsonify({"error": "Missing required fields: session_id, artisan_name, description, craft_type, budget_category_products"}), 400

        if session_id not in session_store:
            return jsonify({"error": "Session ID not found. Please upload images first."}), 404

        # --- NEW: Ensure session is for an artisan listing based on upload_type ---
        if session_store[session_id].get("upload_type") != "artisans":
            return jsonify({"error": "Session ID is not for an artisan listing. Please start a new artisan listing."}), 400
        # --- END NEW ---

        # --- Input Validation ---
        is_safe, reason = is_description_safe(description)
        if not is_safe:
            return jsonify({
                "error": f"Description rejected due to inappropriate content: {reason}",
                "action": "Please revise your description."
            }), 400

        if not isinstance(spoken_languages, list) or not all(isinstance(l, str) for l in spoken_languages):
            return jsonify({"error": "spoken_languages must be a list of strings."}), 400
        if budget_category_products not in ['low', 'mid', 'high']:
            return jsonify({"error": "budget_category_products must be 'low', 'mid', or 'high'."}), 400
        if open_to_visits is not None and not isinstance(open_to_visits, bool):
            return jsonify({"error": "open_to_visits must be a boolean."}), 400
        if offers_workshops is not None and not isinstance(offers_workshops, bool):
            return jsonify({"error": "offers_workshops must be a boolean."}), 400
        if opening_hours is not None and not isinstance(opening_hours, str): # <--- NEW: Validate opening_hours type
            return jsonify({"error": "opening_hours must be a string."}), 400


        tags = extract_tags(description + " " + craft_type) # Extract tags from description and craft type

        # Store artisan details in session_store
        session_store[session_id].update({
            "artisan_name": artisan_name,
            "description": description,
            "craft_type": craft_type,
            "spoken_languages": spoken_languages,
            "budget_category_products": budget_category_products,
            "contact_phone": contact_phone,
            "contact_email": contact_email,
            "open_to_visits": open_to_visits,
            "offers_workshops": offers_workshops,
            "opening_hours": opening_hours, # <--- NEW: Store opening_hours
            "tags": tags,
            "listed_by_uid": user_uid, # Link to the tourist who listed
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "type": "artisan_listing" # Differentiate from hidden gem in session_store (already there)
        })

        return jsonify({
            "message": "Artisan details submitted successfully",
            "session_id": session_id,
            "tags": tags
        }), 200

    @artisan_bp.route('/finalize/<session_id>', methods=['GET'])
    @login_required_user # Only logged-in tourists can finalize their listings
    def finalize_artisan_listing(session_id):
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required to finalize artisan listing."}), 401

        data = session_store.get(session_id)
        # Ensure session is valid and explicitly for an artisan listing
        if not data or data.get("type") != "artisan_listing": 
            return jsonify({"error": "Artisan listing session not found or invalid type."}), 404

        if data.get("listed_by_uid") != user_uid: # Ensure only creator can finalize
            return jsonify({"error": "Unauthorized to finalize this listing."}), 403

        # Use location data from the initial image upload step
        coords = data.get("suggested_location") or data.get("manual_location") or {}

        # image_filenames now correctly contains 'artisans/image.jpg' style paths
        image_filenames = data.get("image_filenames", [])
        preview_image_urls = [f"/uploads/{f}" for f in image_filenames] 

        # Construct the final data preview
        final_data_preview = {
            "artisan_name": data.get("artisan_name"),
            "description": data.get("description"),
            "craft_type": data.get("craft_type"),
            "spoken_languages": data.get("spoken_languages", []),
            "budget_category_products": data.get("budget_category_products"),
            "contact_phone": data.get("contact_phone"),
            "contact_email": data.get("contact_email"),
            "open_to_visits": data.get("open_to_visits"),
            "offers_workshops": data.get("offers_workshops"),
            "opening_hours": data.get('opening_hours'), # <--- NEW: Include opening_hours
            "tags": data.get("tags", []),
            "location": {
                "lat": coords.get("latitude"),
                "lng": coords.get("longitude"),
                "full_address": coords.get("full_address"), # New field for full address
                "address_components": coords.get("address_components")
            },
            "region_name": coords.get("city"), # Use city as the region name
            "state_name": coords.get("state"),
            "image_urls": preview_image_urls,
            "listed_by_uid": data.get("listed_by_uid"),
            "timestamp": data.get("timestamp"),
            "session_id": session_id,
            "source": "image_extracted" if not data.get("gps_fallback") else "manual",
            "status": "pending_review", # Default status for new artisan listings
            "verified_by_lokpath": False
        }

        return jsonify(final_data_preview), 200

    @artisan_bp.route('/upload-to-firebase/<session_id>', methods=['POST'])
    @login_required_user # Only logged-in tourists can finalize their listings
    def upload_artisan_to_firebase(session_id):
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required to upload artisan listing."}), 401

        data = session_store.get(session_id)
        if not data or data.get("type") != "artisan_listing": # <--- NEW: Check upload_type
            return jsonify({"error": "Artisan listing session not found or invalid type."}), 404

        if data.get("listed_by_uid") != user_uid:
            return jsonify({"error": "Unauthorized to finalize this listing."}), 403

        # Extract location data
        coords = data.get("suggested_location") or data.get("manual_location") or {}

        location_data = {
        "lat": coords.get("latitude"),
        "lng": coords.get("longitude"),
        "full_address": coords.get("full_address"),
        "address_components": coords.get("address_components")
        }

        state_name_for_firestore = coords.get("state")
        city_name_for_firestore = coords.get("city")
        if not state_name_for_firestore: state_name_for_firestore = "Unknown_State"
        if not city_name_for_firestore: city_name_for_firestore = "Unknown_City"

        # image_filenames now correctly contains 'artisans/image.jpg' style paths
        image_paths_for_firestore = [f"/uploads/{f}" for f in data.get("image_filenames", [])]

        # Construct the final artisan document
        artisan_document = {
            "artisan_name": data.get("artisan_name"),
            "description": data.get("description"),
            "craft_type": data.get("craft_type"),
            "spoken_languages": data.get("spoken_languages", []),
            "budget_category_products": data.get("budget_category_products"),
            "contact_phone": data.get("contact_phone"),
            "contact_email": data.get("contact_email"),
            "open_to_visits": data.get("open_to_visits"),
            "offers_workshops": data.get("offers_workshops"),
            "opening_hours": data.get('opening_hours'), # <--- NEW: Include opening_hours
            "tags": data.get("tags", []),
            "location": location_data,
            "region_name": city_name_for_firestore,
            "state_name": state_name_for_firestore,
            "image_urls": image_paths_for_firestore, # These now correctly point to uploads/artisans/
            "listed_by_uid": user_uid, # Confirmed as current user
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), # Re-timestamp on final upload
            "status": "pending_review", # Default status for new artisan listings
            "verified_by_lokpath": False, # To be updated by admin after review
            "source_session_id": session_id # Keep for reference
        }

        try:
            # Store in 'artisans' collection
            artisan_listing_id = str(uuid.uuid4()) # A new UUID for the final artisan document
            db_instance.collection('artisans').document(artisan_listing_id).set(artisan_document)
            current_app.logger.info(f"Artisan listing {artisan_listing_id} uploaded to Firebase by {user_uid}.")

            # Increment count on user's profile for "artisans listed"
            user_profile_ref = db_instance.collection('users').document(user_uid)
            # Ensure 'artisans_listed_count' exists and is initialized to 0 in user profile.
            user_profile_ref.update({'artisans_listed_count': firestore.Increment(1)}) 
            current_app.logger.info(f"User {user_uid} artisans_listed_count incremented.")

            # Clean up session store
            del session_store[session_id]
            current_app.logger.info(f"Artisan listing session {session_id} finalized and removed from session_store.")

            return jsonify({"message": "Artisan listing submitted successfully!", "artisan_id": artisan_listing_id}), 201

        except Exception as e:
            current_app.logger.error(f"Error uploading artisan listing {session_id} to Firebase: {e}", exc_info=True)
            return jsonify({"error": "Failed to submit artisan listing.", "details": str(e)}), 500

    return artisan_bp