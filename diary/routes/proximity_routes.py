from flask import Blueprint, request, jsonify
from diary.services.proximity_optimizer import optimize_itinerary_by_proximity

def create_proximity_bp(db):
    """Create and return proximity blueprint with database instance"""
    # ✅ Create Blueprint for proximity-related routes
    proximity_bp = Blueprint("proximity_bp", __name__, url_prefix="/proximity")

    @proximity_bp.route("/optimize-itinerary", methods=["POST"])
    def optimize_itinerary():
        """
        API Route: /optimize-itinerary
        Query Params:
          - user_id: ID of the user
          - trip_id: ID of the trip
          - commit (optional): if 'false', do not update Firestore, just return result
        """

        user_id = request.args.get("user_id")
        trip_id = request.args.get("trip_id")
        commit_flag = request.args.get("commit", "true").lower() != "false"  # Defaults to True

        if not user_id or not trip_id:
            return jsonify({"error": "Missing user_id or trip_id"}), 400

        try:
            result = optimize_itinerary_by_proximity(user_id, trip_id)

            if not result:
                return jsonify({"error": "Itinerary not found or no POIs to optimize."}), 404

            if not commit_flag:
                return jsonify({
                    "message": "Optimized itinerary preview (not saved)",
                    "optimized_itinerary": result
                }), 200

            return jsonify({
                "message": f"Itinerary for user '{user_id}' updated successfully.",
                "trip_id": trip_id
            }), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return proximity_bp
