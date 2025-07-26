# user_auth/routes.py
from flask import Blueprint, request, jsonify, session, current_app
from firebase_admin import firestore, auth # Keep auth, firestore
from .utils import login_required_user
import datetime

# --- HIGHLIGHTED CHANGE START ---
# REMOVE THIS LINE:
# db = firestore.client() # Get the Firestore client initialized in app.py

# ADD THIS FUNCTION:
def create_user_bp(db_instance): # This function will now create and return the blueprint
    user_bp = Blueprint('user_bp', __name__, url_prefix='/user')

    # All routes that use 'db' should now use 'db_instance'

    @user_bp.route('/profile', methods=['GET'])
    @login_required_user
    def get_user_profile():
        user_uid = session.get('user_uid')
        if not user_uid:
            current_app.logger.error("User UID not found in session, despite login_required_user decorator.")
            return jsonify({"error": "Authentication error."}), 500

        user_ref = db_instance.collection('users').document(user_uid) # MODIFIED: use db_instance
        user_doc = user_ref.get()

        if user_doc.exists:
            profile_data = user_doc.to_dict()
            try:
                firebase_user = auth.get_user(user_uid)
                profile_data['email'] = firebase_user.email
                profile_data['phone_number'] = firebase_user.phone_number
                profile_data['display_name'] = firebase_user.display_name if firebase_user.display_name else profile_data.get('name', 'User')
                profile_data['photo_url'] = firebase_user.photo_url
            except auth.UserNotFoundError:
                current_app.logger.warning(f"Firebase Auth user {user_uid} not found, fetching only Firestore data.")
            except Exception as e:
                current_app.logger.error(f"Error fetching Firebase Auth user details for {user_uid}: {e}")

            return jsonify({"message": "User profile retrieved successfully", "profile": profile_data}), 200
        else:
            try:
                firebase_user = auth.get_user(user_uid)
                basic_profile = {
                    "uid": user_uid,
                    "email": firebase_user.email,
                    "phone_number": firebase_user.phone_number,
                    "display_name": firebase_user.display_name,
                    "photo_url": firebase_user.photo_url,
                    "message": "User profile not fully set up. Please complete your profile."
                }
                return jsonify(basic_profile), 200
            except auth.UserNotFoundError:
                return jsonify({"error": "User not found in Firebase Auth either."}), 404
            except Exception as e:
                current_app.logger.error(f"Error fetching Firebase Auth user on profile not found: {e}")
                return jsonify({"error": "Could not retrieve basic user info."}), 500


    @user_bp.route('/profile', methods=['POST'])
    @login_required_user
    def update_user_profile():
        user_uid = session.get('user_uid')
        if not user_uid:
            current_app.logger.error("User UID not found in session for profile update.")
            return jsonify({"error": "Authentication error."}), 500

        data = request.get_json()

        allowed_fields = [
            'name', 'preferred_language', 'hometown', 'interests', 
            'travel_style', # Keep this here
            'accessibility_needs', 'bio', 'profile_image_url'
        ]

        profile_update_data = {}
        for field in allowed_fields:
            if field in data:
                profile_update_data[field] = data[field]

        if 'interests' in profile_update_data and not isinstance(profile_update_data['interests'], list):
            return jsonify({"error": "Interests must be a list of strings."}), 400
        # Add validation for travel_style if it's in allowed_fields
        if 'travel_style' in profile_update_data and not isinstance(profile_update_data['travel_style'], list):
            return jsonify({"error": "Travel style must be a list of strings."}), 400
        if 'accessibility_needs' in profile_update_data and not isinstance(profile_update_data['accessibility_needs'], dict):
            return jsonify({"error": "Accessibility needs must be an object."}), 400

        user_ref = db_instance.collection('users').document(user_uid) # MODIFIED: use db_instance

        user_doc = user_ref.get()
        if not user_doc.exists:
            profile_update_data['joined_date'] = firestore.SERVER_TIMESTAMP
            profile_update_data['submitted_gems_count'] = 0
            profile_update_data['saved_gems'] = []
            profile_update_data['reviewed_gems'] = []

        profile_update_data['last_active'] = firestore.SERVER_TIMESTAMP

        try:
            user_ref.set(profile_update_data, merge=True)
            return jsonify({"message": "User profile updated successfully"}), 200
        except Exception as e:
            current_app.logger.error(f"Error updating user profile for {user_uid}: {e}")
            return jsonify({"error": "Failed to update user profile"}), 500
    
    return user_bp # NEW: Return the blueprint object
# --- HIGHLIGHTED CHANGE END ---