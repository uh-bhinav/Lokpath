from diary.firebase.firebase_config import db
from datetime import datetime
from firebase_admin import firestore

from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from diary.services.post_uploader import upload_post

community_post_bp = Blueprint("community_post", __name__)

@community_post_bp.route("/upload-post", methods=["POST"])
def upload_post_route():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file part in request"}), 400
        
        file = request.files["file"]
        caption = request.form.get("caption", "")
        user_uid = request.form.get("user_uid", "")
        visibility = request.form.get("visibility", "public")

        if not user_uid or not caption:
            return jsonify({"error": "caption and user_uid are required"}), 400

        result = upload_post(file, caption, user_uid, visibility)
        return jsonify({"message": "Post created successfully", "data": result}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@community_post_bp.route("/user-posts/<user_uid>", methods=["GET"])
def get_posts_by_user(user_uid):
    try:
        posts_ref = db.collection("community_posts").where("user_uid", "==", user_uid)
        posts = posts_ref.stream()

        result = []
        for post in posts:
            data = post.to_dict()
            data["post_id"] = post.id
            result.append(data)

        return jsonify({"user_uid": user_uid, "posts": result}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@community_post_bp.route("/community-feed", methods=["GET"])
def get_community_feed():
    try:
        limit = int(request.args.get("limit", 10))
        last_timestamp = request.args.get("last_timestamp")

        posts_ref = db.collection("community_posts").order_by("timestamp", direction="DESCENDING")

        if last_timestamp:
            last_timestamp_obj = datetime.fromisoformat(last_timestamp)
            posts_ref = posts_ref.start_after({"timestamp": last_timestamp_obj})

        posts = posts_ref.limit(limit).stream()

        result = []
        for post in posts:
            data = post.to_dict()
            data["post_id"] = post.id
            result.append(data)

        return jsonify({"posts": result}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
