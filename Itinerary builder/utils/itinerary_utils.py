# utils/itinerary_utils.py

from datetime import datetime

def estimate_required_pois(start_date, end_date):
    """
    Estimate how many POIs are required to fill the itinerary.
    Currently assumes 2 POIs per day.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    num_days = (end - start).days + 1
    return num_days * 2  # ✅ 2 POIs per day

def infer_kid_friendly(tags):
    """
    Infer if a place is kid-friendly based on its tags.
    """
    kid_friendly_tags = ["family-friendly", "safe", "peaceful", "nature", "cultural"]
    not_kid_friendly_tags = ["crowded", "adventurous", "trek", "romantic"]
    
    if any(tag in kid_friendly_tags for tag in tags):
        return True
    elif any(tag in not_kid_friendly_tags for tag in tags):
        return False
    else:
        return None  # Unknown

def estimate_required_pois(start_date, end_date, pois_per_day=3):
    """
    Estimate how many POIs are needed based on trip duration.
    Default: 3 POIs per day (adjustable for scaling).
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days + 1
    return days * pois_per_day
