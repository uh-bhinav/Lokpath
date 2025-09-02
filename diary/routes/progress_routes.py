from flask import Blueprint, request, jsonify
from diary.services.proximity_optimizer import optimize_itinerary_by_proximity
from diary.utils.firestore_paths import itineraries_col, itinerary_doc

def create_progress_bp(db):
    """Create and return progress blueprint with database instance"""
    progress_bp = Blueprint("progress", __name__, url_prefix="/progress")

   # In progress_routes.py

    @progress_bp.route("/save-itinerary", methods=["POST"])
    def save_itinerary():
        try:
            data = request.get_json()
            user_id = data.get("user_id")
            trip_id = data.get("trip_id")
            # itinerary = data.get("itinerary") # This is not used in the optimization flow

            if not user_id or not trip_id:
                return jsonify({"error": "Missing user_id or trip_id"}), 400

            # ## MODIFIED: Define budgets to pass to the optimizer
            # In a real app, these values might come from the user's profile or request body
            activity_budget = 7.5  # Default moderate pace
            travel_budget = 2.0    # Default leisurely travel

            # This part of your logic triggers the optimization
            ref = itinerary_doc(user_id, trip_id)
            snap = ref.get()
            if not snap.exists:
                return jsonify({"error": "Itinerary not found"}), 404
            
            # ## MODIFIED: Pass the budgets to the optimizer function
            optimized = optimize_itinerary_by_proximity(
                user_id,
                trip_id,
                daily_time_budget=activity_budget,
                max_daily_travel_hours=travel_budget
            )
            
            return jsonify({
                "message": "Itinerary optimized successfully",
                "trip_id": trip_id, 
                "itinerary": optimized
            }), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @progress_bp.route("/user-itineraries/<user_id>", methods=["GET"])
    def get_user_itineraries(user_id):
        try:
            itineraries_ref = itineraries_col(user_id)
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
            itinerary_ref = itinerary_doc(user_id, trip_id)
            doc = itinerary_ref.get()

            if not doc.exists:
                return jsonify({"error": "Itinerary not found"}), 404

            itinerary = doc.to_dict()
            return jsonify({"trip_id": trip_id, "itinerary": itinerary}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return progress_bp