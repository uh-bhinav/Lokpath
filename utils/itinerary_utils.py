# utils/itinerary_utils.py

from datetime import datetime

def estimate_required_pois(start_date, end_date):
    """
    Estimate how many POIs are required to fill the itinerary.
    Currently assumes 1 POI per day.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    num_days = (end - start).days + 1
    return num_days
