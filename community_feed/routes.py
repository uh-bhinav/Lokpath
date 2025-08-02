# community_feed/routes.py
from flask import Blueprint, request, jsonify, session, current_app
from firebase_admin import firestore
from user_auth.utils import login_required_user
import datetime
import uuid

def create_community_bp(db_instance): # Function to create and return the blueprint
    community_bp = Blueprint('community_bp', __name__, url_prefix='/community')

    @community_bp.route('/feed', methods=['GET'])
    def get_community_feed():
        # Public endpoint for all users to see
        user_uid = session.get('user_uid')
        current_app.logger.info(f"Community feed requested by UID: {user_uid}")

        try:
            feed_query = db_instance.collection('community_posts').where('status', '==', 'approved').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(20)

            posts = []
            for doc in feed_query.stream():
                post_data = doc.to_dict()
                posts.append({
                    "post_id": doc.id,
                    "content": post_data.get('content'),
                    "image_url": post_data.get('image_url'),
                    "timestamp": post_data.get('timestamp'),
                    "user_uid": post_data.get('user_uid')
                })

            return jsonify({"message": "Community feed retrieved successfully", "feed": posts}), 200

        except Exception as e:
            current_app.logger.error(f"Error retrieving community feed: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve community feed."}), 500


    @community_bp.route('/post', methods=['POST'])
    @login_required_user
    def create_community_post():
        user_uid = session.get('user_uid')
        if not user_uid:
            return jsonify({"error": "Authentication required."}), 401

        data = request.get_json()
        content = data.get('content')
        image_url = data.get('image_url') # Assuming image has been pre-uploaded to Firebase Storage

        if not content and not image_url:
            return jsonify({"error": "Post must contain text and an image."}), 400

        try:
            post_id = str(uuid.uuid4())
            post_data = {
                "user_uid": user_uid,
                "content": content,
                "image_url": image_url,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "status": "approved" # For now, assume all posts are approved.
                                    # A future step would be moderation to set this to 'pending_review'
            }
            db_instance.collection('community_posts').document(post_id).set(post_data)

            return jsonify({"message": "Post created successfully!", "post_id": post_id}), 201

        except Exception as e:
            current_app.logger.error(f"Error creating community post for user {user_uid}: {e}", exc_info=True)
            return jsonify({"error": "Failed to create post.", "details": str(e)}), 500

    return community_bp