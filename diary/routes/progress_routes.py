from flask import Blueprint, request, jsonify
from datetime import datetime
import uuid

def create_progress_bp(db):
    """Create and return progress blueprint with database instance"""
    progress_bp = Blueprint("progress", __name__, url_prefix="/progress")

    @progress_bp.route("/save-itinerary", methods=["POST"])
    def save_itinerary():
        try:
            data = request.get_json()
            user_id = data.get("user_id")
            itinerary = data.get("itinerary")

            if not user_id or not itinerary:
                return jsonify({"error": "Missing user_id or itinerary"}), 400

            trip_id = str(uuid.uuid4())
            itinerary["created_at"] = datetime.now().isoformat()
            itinerary["trip_id"] = trip_id

            doc_ref = db.collection("diary").document(user_id).collection("itineraries").document(trip_id)
            doc_ref.set(itinerary)

            return jsonify({"message": "Itinerary saved successfully", "trip_id": trip_id}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @progress_bp.route("/user-itineraries/<user_id>", methods=["GET"])
    def get_user_itineraries(user_id):
        try:
            itineraries_ref = db.collection("diary").document(user_id).collection("itineraries")
            docs = itineraries_ref.stream()

            result = []
            for doc in docs:
                data = doc.to_dict()
                result.append({
                    "trip_id": data.get("trip_id"),
                    "trip_name": data.get("trip_name"),
                    "location": data.get("location"),
                    "start_date": data.get("start_date"),
                    "end_date": data.get("end_date"),
                    "created_at": data.get("created_at")
                })

            return jsonify({"user_id": user_id, "itineraries": result}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @progress_bp.route("/user-itinerary/<user_id>/<trip_id>", methods=["GET"])
    def get_itinerary_by_id(user_id, trip_id):
        try:
            itinerary_ref = db.collection("diary").document(user_id).collection("itineraries").document(trip_id)
            doc = itinerary_ref.get()

            if not doc.exists:
                return jsonify({"error": "Itinerary not found"}), 404

            itinerary = doc.to_dict()
            return jsonify({"trip_id": trip_id, "itinerary": itinerary}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return progress_bp