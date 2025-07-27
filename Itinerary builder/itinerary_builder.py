# itinerary_builder.py
from datetime import datetime, timedelta

# Mapping tags to a rough "best time" description.  These are
# intentionally broad so the itinerary only suggests the general part
# of the day rather than a strict schedule.
TAG_TO_BEST_TIME = {
    "sunset": "Sunset",
    "sunrise": "Sunrise",
    "trek": "Morning",
    "shopping": "Afternoon",
    "romantic": "Evening",
    "culture": "Morning",
    "wildlife": "Morning",
    "religious": "Morning",
    "adventure": "Morning",
    "food": "Afternoon",
}

def generate_itinerary(filtered_pois, start_date, end_date, enable_hidden_gems=False, max_per_day=2):
    """
    Generate a scalable itinerary without attaching fixed dates.
    Distributes POIs across available days and includes disclaimers + photos.
    ``max_per_day`` controls how many POIs can be assigned to a single day.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    num_days = (end - start).days + 1

    # ✅ Instead of dates, we use day indices (Day 1, Day 2...)
    itinerary = {f"Day {i+1}": [] for i in range(num_days)}
    current_day_idx = 0
    current_day_count = 0
    day_keys = list(itinerary.keys())

    for poi in filtered_pois:
        if current_day_idx >= len(day_keys):
            break
        # Move to next day if the current one is filled
        if current_day_count >= max_per_day:
            current_day_idx += 1
            current_day_count = 0
            if current_day_idx >= len(day_keys):
                break

        # ✅ Determine best time to visit
        best_time = poi.get("best_time") or "Anytime"
        if best_time == "Anytime":
            for tag in poi.get("tags", []):
                if tag in TAG_TO_BEST_TIME:
                    best_time = TAG_TO_BEST_TIME[tag]
                    break

        activity = {
            "name": poi["name"],
            "tags": poi.get("tags", []),
            "best_time": best_time,
            "budget_category": poi.get("budget_category", "unknown"),
            "disclaimer": poi.get("disclaimer", ""),
            "photo_url": poi.get("photo_url", ""),
            "coordinates": poi.get("coordinates", {})  # ✅ For future route optimization
        }

        itinerary[day_keys[current_day_idx]].append(activity)
        current_day_count += 1

    # ✅ Inject Hidden Gems Placeholder
    if enable_hidden_gems:
        for day in reversed(day_keys):
            if not itinerary[day]:
                itinerary[day].append({
                    "name": "🔍 Hidden Gem (Coming Soon)",
                    "tags": ["surprise", "offbeat"],
                    "best_time": "Anytime",
                    "disclaimer": "⏳ This feature is under development"
                })
                break

    return itinerary
