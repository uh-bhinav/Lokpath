from flask import Blueprint, request, jsonify
from firebase_admin import firestore
# from diary.firebase.firebase_config import db
from diary.services.diary_photo_uploader import upload_diary_photo
from diary.services.proximity_optimizer import optimize_itinerary_by_proximity
import os
import uuid

import uuid
import os
def create_user_itinerary_bp(db):
    user_itinerary_bp = Blueprint('user_itinerary', __name__,url_prefix="/user-itinerary")
    



    # ❌ REDUNDANT: More robust version exists in diary_routes.py
    # @diary_bp.route("/user-itinerary/<user_id>/<trip_id>", methods=["PUT"])
    # def save_user_itinerary(user_id, trip_id):
    #     """Save or update a user's itinerary"""
    #     try:
    #         itinerary_data = request.get_json()
    #         if not itinerary_data:
    #             return jsonify({"error": "No itinerary data provided"}), 400
    # 
    #         # Save to Firestore
    #         doc_ref = db.collection("diary").document(user_id).collection("itineraries").document(trip_id)
    #         doc_ref.set(itinerary_data)
    # 
    #         return jsonify({
    #             "message": "Itinerary saved successfully",
    #             "user_id": user_id,
    #             "trip_id": trip_id
    #         }), 200
    # 
    #     except Exception as e:
    #         return jsonify({"error": str(e)}), 500

    # ❌ REDUNDANT: More robust version exists in diary_routes.py
    # @diary_bp.route("/user-itinerary/<user_id>/<trip_id>", methods=["DELETE"])
    # def delete_user_itinerary(user_id, trip_id):
    #     """Delete a user's itinerary"""
    #     try:
    #         doc_ref = db.collection("diary").document(user_id).collection("itineraries").document(trip_id)
    #         
    #         # Check if exists
    #         doc = doc_ref.get()
    #         if not doc.exists:
    #             return jsonify({"error": "Itinerary not found"}), 404
    # 
    #         # Delete the document
    #         doc_ref.delete()
    # 
    #         return jsonify({
    #             "message": "Itinerary deleted successfully",
    #             "user_id": user_id,
    #             "trip_id": trip_id
    #         }), 200
    # 
    #     except Exception as e:
    #         return jsonify({"error": str(e)}), 500

    # ❌ REDUNDANT: More robust version exists in diary_routes.py
    # @diary_bp.route("/user-itinerary/<user_id>/<trip_id>/upload-photo", methods=["POST"])
    # def upload_diary_photo_route(user_id, trip_id):
    #     """Upload a photo to a trip's diary"""
    #     try:
    #         if "file" not in request.files:
    #             return jsonify({"error": "No file part"}), 400
    #         
    #         file = request.files["file"]
    #         caption = request.form.get("caption", "")
    # 
    #         # Check if itinerary exists
    #         itinerary_ref = db.collection("diary").document(user_id).collection("itineraries").document(trip_id)
    #         if not itinerary_ref.get().exists:
    #             return jsonify({"error": "Itinerary not found"}), 404
    # 
    #         # Upload photo and get metadata
    #         photo_info = upload_diary_photo(file, user_id, trip_id, caption)
    # 
    #         # Store metadata in Firestore subcollection
    #         photo_id = photo_info["photo_id"]
    #         db.collection("diary").document(user_id)\
    #             .collection("itineraries").document(trip_id)\
    #             .collection("diary_photos").document(photo_id)\
    #             .set(photo_info)
    # 
    #         return jsonify({
    #             "message": "Photo uploaded successfully", 
    #             "photo_id": photo_id, 
    #             "data": photo_info
    #         }), 200
    # 
    #     except Exception as e:
    #         return jsonify({"error": str(e)}), 500

    # ❌ REDUNDANT: More robust version exists in diary_routes.py
    # @diary_bp.route("/user-itinerary/<user_id>/<trip_id>/photos", methods=["GET"])
    # def get_diary_photos(user_id, trip_id):
    #     """Get all photos for a trip"""
    #     try:
    #         photo_ref = db.collection("diary").document(user_id)\
    #             .collection("itineraries").document(trip_id)\
    #             .collection("diary_photos")
    #         
    #         photos = photo_ref.order_by("timestamp").stream()
    # 
    #         photo_list = []
    #         for photo in photos:
    #             data = photo.to_dict()
    #             photo_list.append({
    #                 "photo_id": photo.id,
    #                 "url": data.get("url"),
    #                 "caption": data.get("caption", ""),
    #                 "timestamp": data.get("timestamp"),
    #                 "gps": data.get("gps"),
    #                 "file_type": data.get("file_type")
    #             })
    # 
    #         return jsonify({"photos": photo_list, "count": len(photo_list)}), 200
    # 
    #     except Exception as e:
    #         return jsonify({"error": str(e)}), 500

    # ❌ REDUNDANT: More robust version exists in diary_routes.py
    # @diary_bp.route("/user-itinerary/<user_id>/<trip_id>/photos/<photo_id>", methods=["DELETE"])
    # def delete_diary_photo(user_id, trip_id, photo_id):
    #     """Delete a specific photo from a trip"""
    #     try:
    #         # Get photo reference
    #         photo_ref = db.collection("diary").document(user_id)\
    #             .collection("itineraries").document(trip_id)\
    #             .collection("diary_photos").document(photo_id)
    # 
    #         doc = photo_ref.get()
    #         if not doc.exists:
    #             return jsonify({"error": "Photo not found"}), 404
    # 
    #         photo_data = doc.to_dict()
    #         
    #         # Delete file from disk
    #         file_path = photo_data.get("url", "").lstrip("/")
    #         if file_path and os.path.exists(file_path):
    #             os.remove(file_path)
    # 
    #         # Delete from Firestore
    #         photo_ref.delete()
    # 
    #         return jsonify({"message": "Photo deleted successfully"}), 200
    # 
    #     except Exception as e:
    #         return jsonify({"error": str(e)}), 500
        
    # ❌ REDUNDANT: More robust version exists in diary_routes.py
    # @diary_bp.route("/user-itinerary/<user_id>/<trip_id>/timeline", methods=["GET"])
    # def get_trip_timeline(user_id, trip_id):
    #     """Get chronological timeline of photos for a trip"""
    #     try:
    #         # Reference the diary_photos subcollection
    #         photo_ref = db.collection("diary").document(user_id)\
    #             .collection("itineraries").document(trip_id)\
    #             .collection("diary_photos")
    # 
    #         # Fetch all photos sorted by timestamp
    #         photos = photo_ref.order_by("timestamp").stream()
    # 
    #         timeline = []
    #         for photo in photos:
    #             data = photo.to_dict()
    #             timeline.append({
    #                 "photo_id": photo.id,
    #                 "url": data.get("url"),
    #                 "caption": data.get("caption", ""),
    #                 "timestamp": data.get("timestamp"),
    #                 "gps": data.get("gps", None),
    #                 "file_type": data.get("file_type"),
    #                 "exif_timestamp": data.get("exif_timestamp"),
    #                 "upload_timestamp": data.get("upload_timestamp")
    #             })
    # 
    #         return jsonify({
    #             "trip_id": trip_id,
    #             "user_id": user_id,
    #             "photo_count": len(timeline),
    #             "timeline": timeline
    #         }), 200
    # 
    #     except Exception as e:
    #         return jsonify({"error": str(e)}), 500

    # ❌ REDUNDANT: More robust version exists in diary_routes.py (also has duplicate entry bug)
    # @diary_bp.route("/user-itinerary/<user_id>/<trip_id>/locations", methods=["GET"])
    # def get_location_summary(user_id, trip_id):
    #     """Get summary of GPS-tagged photos for mapping"""
    #     try:
    #         photo_ref = db.collection("diary").document(user_id)\
    #             .collection("itineraries").document(trip_id)\
    #             .collection("diary_photos")
    # 
    #         photos = photo_ref.stream()
    #         
    #         gps_photos = []
    #         for photo in photos:
    #             data = photo.to_dict()
    #             if data.get("gps"):
    #                 gps_photos.append({
    #                     "photo_id": photo.id,
    #                     "caption": data.get("caption", ""),
    #                     "gps": data.get("gps"),
    #                     "timestamp": data.get("timestamp"),
    #                     "url": data.get("url")
    #                 })
    #                 # 🐛 BUG: This line duplicates entries!
    #                 gps_photos.append({
    #                     "photo_id": photo.id,
    #                     "caption": data.get("caption", ""),
    #                     "gps": data.get("gps"),
    #                     "timestamp": data.get("timestamp"),
    #                     "url": data.get("url")
    #                 })
    # 
    #         return jsonify({
    #             "trip_id": trip_id,
    #             "total_photos": len(gps_photos),
    #             "gps_photos": gps_photos
    #         }), 200
    # 
    #     except Exception as e:
    #         return jsonify({"error": str(e)}), 500

    # ✅ UNIQUE: Keep this route - proximity optimization is only available here
    # @user_itinerary_bp.route('/<user_id>/<trip_id>/proximity-optimize', methods=['POST'])
    # def proximity_optimize(user_id, trip_id):
    #     try:
    #         new_itinerary = optimize_itinerary_by_proximity(user_id, trip_id)

    #         if not new_itinerary:
    #             return jsonify({"error": "Optimization failed or no POIs found"}), 404

    #         return jsonify({
    #             "success": True,
    #             "message": "Itinerary optimized based on proximity.",
    #             "data": new_itinerary
    #         }), 200
    #     except Exception as e:
    #         return jsonify({"error": str(e)}), 500
    # return user_itinerary_bp