from flask import Flask, send_from_directory, jsonify
from diary.routes.proximity_routes import create_proximity_bp
from diary.routes.community_post_routes import create_community_post_bp # This one was already a direct blueprint
from diary.routes.progress_routes import create_progress_bp
from diary.routes.diary_routes import create_diary_bp
from diary.routes.user_itinerary_routes import  create_user_itinerary_bp
import os
import json
from diary.firebase.firebase_config import db

def create_app():
    app = Flask(__name__)
    proximity_bp=create_proximity_bp(db)
    progress_bp=create_progress_bp(db)
    diary_bp=create_diary_bp(db)
    community_post_bp=create_community_post_bp(db)
    user_itinerary_bp=create_user_itinerary_bp(db)

    # ✅ Register Blueprints
    app.register_blueprint(proximity_bp)
    app.register_blueprint(community_post_bp)
    app.register_blueprint(progress_bp)
    app.register_blueprint(diary_bp)
    app.register_blueprint(user_itinerary_bp)

    # ✅ Static route to serve uploaded images
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        return send_from_directory("uploads", filename)
    @app.route("/user-itinerary/<user_id>/diary-feed", methods=["GET"])
    def diary_feed(user_id):
        root_path = os.path.join("uploads", "diary_photos", user_id)
        if not os.path.exists(root_path):
            return jsonify({"message": "No trips found", "photos": []})

        all_photos = []

        for trip_id in os.listdir(root_path):
            trip_folder = os.path.join(root_path, trip_id)
            meta_file = os.path.join(trip_folder, "photo_metadata.json")

            if os.path.exists(meta_file):
                with open(meta_file, "r") as f:
                    try:
                        trip_photos = json.load(f)
                        for p in trip_photos:
                            p["trip_id"] = trip_id  # 🧩 Add context
                            all_photos.append(p)
                    except Exception as e:
                        print(f"Error loading metadata for {trip_id}: {e}")

        # Sort by timestamp descending
        all_photos.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return jsonify({
            "user_id": user_id,
            "photo_count": len(all_photos),
            "photos": all_photos
        })


    return app


# ✅ Run the app if executed directly
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5001)  # Changed from 5000 to avoid AirPlay conflict
