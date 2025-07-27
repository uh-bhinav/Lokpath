# utils/itinerary_utils.py

from datetime import datetime


def infer_kid_friendly(tags):
    """Return a guess whether a POI is kid friendly based on its tags.

    The function returns ``True`` if the tags explicitly contain
    ``"family-friendly"``.  If tags indicate potentially risky
    activities (for example ``"trek"`` or ``"adventurous"``) the
    function returns ``False``.  If no clear indication is found,
    ``None`` is returned which signals that suitability for kids is
    unknown.
    """

    tag_set = set(t.lower() for t in tags or [])

    if "family-friendly" in tag_set:
        return True

    risky = {"trek", "adventurous", "nightlife"}
    if tag_set.intersection(risky):
        return False

    return None

def estimate_required_pois(start_date, end_date, pois_per_day=3):
    """
    Estimate how many POIs are needed based on trip duration.
    Default: 3 POIs per day (adjustable for scaling).
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days + 1
    return days * pois_per_day
