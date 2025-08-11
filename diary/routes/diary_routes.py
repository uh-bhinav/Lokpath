from flask import Blueprint, request, jsonify
# from diary.firebase.firebase_config import db
from diary.services.diary_photo_uploader import upload_diary_photo
from diary.services.firestore_photo_storage import (
    get_photos_from_firestore, 
    delete_photo_from_firestore
)
from collections import defaultdict
from datetime import datetime
import uuid
import os

def create_diary_bp(db):
    """Create and return diary blueprint with database instance"""
    # Create the blueprint
    diary_bp = Blueprint("diary_bp", __name__, url_prefix="/diary")
    
    @diary_bp.route("/user-itinerary/<user_id>/<trip_id>", methods=["PUT"])
    def update_user_itinerary(user_id, trip_id):
        """Update itinerary metadata"""
        try:
            updated_data = request.json

            if not updated_data:
                return jsonify({"error": "No data provided"}), 400

            doc_ref = db.collection("diary").document(user_id).collection("itineraries").document(trip_id)

            # Check if itinerary exists
            if not doc_ref.get().exists:
                return jsonify({"error": "Itinerary not found"}), 404

            # Update Firestore document
            doc_ref.update(updated_data)

            return jsonify({"message": "Itinerary updated successfully"}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @diary_bp.route("/user-itinerary/<user_id>/<trip_id>", methods=["DELETE"])
    def delete_user_itinerary(user_id, trip_id):
        """Delete an entire itinerary and all its photos"""
        try:
            doc_ref = db.collection("diary").document(user_id).collection("itineraries").document(trip_id)

            # Check if itinerary exists
            if not doc_ref.get().exists:
                return jsonify({"error": "Itinerary not found"}), 404

            # Delete all photos in the itinerary first
            photos_ref = doc_ref.collection("photos")
            photos = photos_ref.stream()
            
            for photo_doc in photos:
                photo_data = photo_doc.to_dict()
                file_path = photo_data.get("url", "").lstrip("/")
                
                # Delete file from disk
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                
                # Delete photo document
                photo_doc.reference.delete()

            # Delete the itinerary document
            doc_ref.delete()

            return jsonify({"message": "Itinerary and all photos deleted successfully"}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @diary_bp.route("/user-itinerary/<user_id>/<trip_id>/upload-photo", methods=["POST"])
    def upload_diary_photo_route(user_id, trip_id):
        """
        Upload a photo with GPS and EXIF extraction
        
        Test with:
        curl -X POST http://127.0.0.1:5000/user-itinerary/user_123/07c2f0d4/upload-photo \
        -F "file=@/path/to/photo.HEIC" \
        -F "caption=Sunset from the peak"
        """
        try:
            if "file" not in request.files:
                return jsonify({"error": "No file part"}), 400
            
            file = request.files["file"]
            if file.filename == '':
                return jsonify({"error": "No file selected"}), 400
                
            caption = request.form.get("caption", "")

            # Check if itinerary exists
            itinerary_ref = db.collection("diary").document(user_id).collection("itineraries").document(trip_id)
            if not itinerary_ref.get().exists:
                return jsonify({"error": "Itinerary not found"}), 404

            # Upload photo and extract metadata
            photo_data = upload_diary_photo(file, user_id, trip_id, caption)
            photo_id = photo_data["photo_id"]

            return jsonify({
                "message": "Photo uploaded successfully", 
                "photo_id": photo_id, 
                "data": photo_data
            }), 200

        except Exception as e:
            return jsonify({"error": f"Upload failed: {str(e)}"}), 500

    @diary_bp.route("/user-itinerary/<user_id>/<trip_id>/photos", methods=["GET"])
    def get_diary_photos(user_id, trip_id):
        """
        Get all photos for a trip
        """
        try:
            photos = get_photos_from_firestore(user_id, trip_id)
            
            return jsonify({
                "photos": photos, 
                "count": len(photos),
                "trip_id": trip_id,
                "user_id": user_id
            }), 200

        except Exception as e:
            return jsonify({"error": f"Failed to fetch photos: {str(e)}"}), 500

    @diary_bp.route("/user-itinerary/<user_id>/<trip_id>/timeline", methods=["GET"])
    def get_user_timeline(user_id, trip_id):
        """
        Get timeline grouped by day, sorted by photo capture time
        
        Test with:
        curl -X GET http://127.0.0.1:5000/user-itinerary/user_123/07c2f0d4-f687-462a-a300-793353548adc/timeline
        """
        try:
            photos = get_photos_from_firestore(user_id, trip_id)
            
            daily_timeline = defaultdict(list)
            photo_count = len(photos)
            photos_with_gps = 0
            photos_without_gps = 0

            for photo in photos:
                timestamp = photo.get("timestamp")
                if not timestamp:
                    continue

                # Extract just the date portion for grouping
                try:
                    # Handle both ISO format and other formats
                    if 'T' in timestamp:
                        date_key = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date().isoformat()
                    else:
                        date_key = datetime.fromisoformat(timestamp).date().isoformat()
                except:
                    # Fallback to current date if parsing fails
                    date_key = datetime.now().date().isoformat()
                
                # Count GPS availability
                if photo.get("has_gps", False):
                    photos_with_gps += 1
                else:
                    photos_without_gps += 1
                
                daily_timeline[date_key].append({
                    "photo_id": photo.get("photo_id"),
                    "caption": photo.get("caption", ""),
                    "url": photo.get("url"),
                    "timestamp": timestamp,
                    "exif_timestamp": photo.get("exif_timestamp"),
                    "gps": photo.get("gps"),
                    "has_gps": photo.get("has_gps", False),
                    "file_type": photo.get("file_type", "Unknown")
                })

            # Sort each day's photos by timestamp
            for date in daily_timeline:
                daily_timeline[date].sort(key=lambda x: x["timestamp"])

            return jsonify({
                "trip_id": trip_id,
                "user_id": user_id,
                "photo_count": photo_count,
                "photos_with_gps": photos_with_gps,
                "photos_without_gps": photos_without_gps,
                "daily_timeline": dict(daily_timeline)
            }), 200

        except Exception as e:
            return jsonify({"error": f"Timeline fetch failed: {str(e)}"}), 500

    @diary_bp.route("/user-itinerary/<user_id>/<trip_id>/photos/<photo_id>", methods=["DELETE"])
    def delete_diary_photo(user_id, trip_id, photo_id):
        """
        Delete a specific photo and its metadata
        """
        try:
            # Get photo metadata first
            photo_ref = (
                db.collection("diary")
                .document(user_id)
                .collection("itineraries")
                .document(trip_id)
                .collection("photos")
                .document(photo_id)
            )

            doc = photo_ref.get()
            if not doc.exists:
                return jsonify({"error": "Photo not found"}), 404

            photo_data = doc.to_dict()
            file_path = photo_data.get("url", "").lstrip("/")

            # Delete file from disk
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                print(f"✅ Deleted file: {file_path}")

            # Delete from Firestore
            success = delete_photo_from_firestore(user_id, trip_id, photo_id)
            
            if success:
                return jsonify({"message": "Photo deleted successfully"}), 200
            else:
                return jsonify({"error": "Failed to delete from database"}), 500

        except Exception as e:
            return jsonify({"error": f"Delete failed: {str(e)}"}), 500

    @diary_bp.route("/user-itinerary/<user_id>/<trip_id>/locations", methods=["GET"])
    def get_location_summary(user_id, trip_id):
        """
        Get location-based summary of photos with GPS data
        Groups photos by approximate location for mapping
        """
        try:
            photos = get_photos_from_firestore(user_id, trip_id)
            
            # Filter photos with GPS and cluster by location
            location_clusters = defaultdict(list)
            
            for photo in photos:
                gps = photo.get("gps")
                if gps and gps.get("lat") and gps.get("lng"):
                    # Round to ~100m precision for clustering
                    lat_key = round(gps["lat"], 3)
                    lng_key = round(gps["lng"], 3)
                    key = (lat_key, lng_key)
                    
                    location_clusters[key].append(photo)

            # Prepare location summary
            location_summary = []
            for (lat, lng), cluster in location_clusters.items():
                # Use earliest photo as representative
                representative = min(cluster, key=lambda x: x.get("timestamp", ""))
                
                location_summary.append({
                    "lat": lat,
                    "lng": lng,
                    "photo_count": len(cluster),
                    "representative": {
                        "photo_id": representative.get("photo_id"),
                        "url": representative.get("url"),
                        "caption": representative.get("caption", ""),
                        "timestamp": representative.get("timestamp")
                    },
                    "all_photos": [
                        {
                            "photo_id": p.get("photo_id"),
                            "caption": p.get("caption", ""),
                            "timestamp": p.get("timestamp")
                        } for p in cluster
                    ]
                })
            
            # Sort by photo count (most photos first)
            location_summary.sort(key=lambda x: x["photo_count"], reverse=True)

            return jsonify({
                "trip_id": trip_id,
                "user_id": user_id,
                "total_locations": len(location_summary),
                "total_geotagged_photos": sum(loc["photo_count"] for loc in location_summary),
                "locations": location_summary
            }), 200

        except Exception as e:
            return jsonify({"error": f"Location summary failed: {str(e)}"}), 500

    @diary_bp.route("/user-itinerary/<user_id>/<trip_id>/stats", methods=["GET"])
    def get_trip_stats(user_id, trip_id):
        """
        Get comprehensive trip statistics
        """
        try:
            photos = get_photos_from_firestore(user_id, trip_id)
            
            total_photos = len(photos)
            photos_with_gps = sum(1 for p in photos if p.get("has_gps", False))
            photos_without_gps = total_photos - photos_with_gps
            
            file_types = defaultdict(int)
            earliest_photo = None
            latest_photo = None
            
            for photo in photos:
                # Count file types
                file_type = photo.get("file_type", "Unknown")
                file_types[file_type] += 1
                
                # Track date range
                timestamp = photo.get("timestamp")
                if timestamp:
                    if not earliest_photo or timestamp < earliest_photo:
                        earliest_photo = timestamp
                    if not latest_photo or timestamp > latest_photo:
                        latest_photo = timestamp

            return jsonify({
                "trip_id": trip_id,
                "user_id": user_id,
                "total_photos": total_photos,
                "photos_with_gps": photos_with_gps,
                "photos_without_gps": photos_without_gps,
                "gps_percentage": round((photos_with_gps / total_photos * 100) if total_photos > 0 else 0, 1),
                "file_types": dict(file_types),
                "date_range": {
                    "earliest": earliest_photo,
                    "latest": latest_photo
                }
            }), 200

        except Exception as e:
            return jsonify({"error": f"Stats fetch failed: {str(e)}"}), 500
    return diary_bp