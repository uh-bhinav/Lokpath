from typing import Dict, Any

from diary.utils.firestore_paths import itinerary_doc
from diary.services.proximity_optimizer import optimize_itinerary_by_proximity


def optimize_then_save_itinerary(user_id: str, trip_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pipeline to persist itinerary data ensuring proximity optimization:
      1) Write incoming payload (trip meta + itinerary).
      2) Run optimizer (reads from the just-written doc).
      3) Persist ONLY the optimized itinerary as authoritative.
      4) Return optimized itinerary for response.
    """
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict with at least an 'itinerary' key")

    # 1) Save incoming payload (includes itinerary, trip_name, dates, etc.)
    itinerary_doc(user_id, trip_id).set(payload, merge=False)

    # 2) Optimize (reads from the just-written doc)
    optimized = optimize_itinerary_by_proximity(user_id, trip_id)

    # 3) Persist final authoritative version
    if optimized:
        itinerary_doc(user_id, trip_id).update({"itinerary": optimized})

    # 4) Return optimized
    return optimized or payload.get("itinerary", {})

