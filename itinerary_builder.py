# itinerary_builder.py
from datetime import datetime, timedelta

# Mapping tags to preferred time slots
TAG_TO_SLOT = {
    "sunset": "17:30–18:30",
    "sunrise": "06:00–07:00",
    "trek": "06:00–09:00",
    "shopping": "14:00–16:00",
    "romantic": "17:00–18:30",
    "culture": "10:00–12:00",
    "wildlife": "08:00–10:00",
    "religious": "09:00–11:00",
    "adventure": "07:00–09:00",
    "food": "13:00–14:30"
}

def generate_itinerary(filtered_pois, start_date, end_date, enable_hidden_gems=False):
    """
    Generate a scalable itinerary without attaching fixed dates.
    Distributes POIs across available days and includes disclaimers + photos.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    num_days = (end - start).days + 1

    # ✅ Instead of dates, we use day indices (Day 1, Day 2...)
    itinerary = {f"Day {i+1}": [] for i in range(num_days)}
    used = set()
    current_day_idx = 0
    day_keys = list(itinerary.keys())

    for poi in filtered_pois:
        if current_day_idx >= len(day_keys):
            break

        # ✅ Select best time slot based on tags
        slot = "Anytime"
        for tag in poi.get("tags", []):
            if tag in TAG_TO_SLOT:
                slot = TAG_TO_SLOT[tag]
                break

        activity = {
            "name": poi["name"],
            "tags": poi.get("tags", []),
            "time_slot": slot,
            "budget_category": poi.get("budget_category", "unknown"),
            "disclaimer": poi.get("disclaimer", ""),
            "photo_url": poi.get("photo_url", ""),
            "coordinates": poi.get("coordinates", {})  # ✅ For future route optimization
        }

        itinerary[day_keys[current_day_idx]].append(activity)
        current_day_idx += 1

    # ✅ Inject Hidden Gems Placeholder
    if enable_hidden_gems:
        for day in reversed(day_keys):
            if not itinerary[day]:
                itinerary[day].append({
                    "name": "🔍 Hidden Gem (Coming Soon)",
                    "tags": ["surprise", "offbeat"],
                    "time_slot": "Anytime",
                    "disclaimer": "⏳ This feature is under development"
                })
                break

    return itinerary
