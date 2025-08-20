# ranking_utils.py

import math
from datetime import datetime

def compute_score(poi: dict) -> float:
    """
    Compute a ranking score for a POI.
    Factors considered:
    - rating (0–5)
    - review_count (logarithmic scaling to avoid bias)
    - recency of update (newer = slight boost)
    - visit_count (user interaction weight)
    """
    rating = poi.get("rating", 0)
    review_count = poi.get("review_count", 0)
    visit_count = poi.get("visit_count", 0)
    updated_at = poi.get("updated_at")

    # Normalize review influence (log scale)
    review_factor = math.log1p(review_count)  

    # Rating weighted more heavily
    base_score = rating * 2.0 + review_factor

    # Add visit count influence
    base_score += math.log1p(visit_count)

    # Recency boost (decays with time)
    if updated_at:
        try:
            updated_time = datetime.fromisoformat(updated_at)
            days_since_update = (datetime.utcnow() - updated_time).days
            recency_boost = max(0.5, 10 / (days_since_update + 1))
            base_score += recency_boost
        except Exception:
            pass

    return round(base_score, 3)


def rank_pois(pois: list) -> list:
    """
    Given a list of POIs (dicts), compute and attach score, then sort.
    """
    ranked_pois = []
    for poi in pois:
        poi["score"] = compute_score(poi)
        ranked_pois.append(poi)

    # Sort descending by score
    ranked_pois.sort(key=lambda x: x["score"], reverse=True)

    return ranked_pois
