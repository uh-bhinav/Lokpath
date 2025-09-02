# proximity_optimizer.py

import math
import sys
import os
from typing import List, Dict, Tuple
from copy import deepcopy

# Fix Python import path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from diary.utils.firestore_paths import itinerary_doc

# --- Distance utilities (No changes here) ---
def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371.0
    lat1, lon1 = a
    lat2, lon2 = b
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    la1 = math.radians(lat1)
    la2 = math.radians(lat2)
    h = (math.sin(d_lat / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(d_lon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))

def build_distance_matrix(coords: List[Tuple[float, float]]) -> List[List[float]]:
    n = len(coords)
    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine_km(coords[i], coords[j])
            dist[i][j] = d
            dist[j][i] = d
    return dist

# --- Global route: NN + 2-Opt (No changes here) ---
def nearest_neighbor_order(dist: List[List[float]], start_idx: int = 0) -> List[int]:
    n = len(dist)
    unvisited = set(range(n))
    order = [start_idx]
    unvisited.remove(start_idx)
    while unvisited:
        last = order[-1]
        nxt = min(unvisited, key=lambda j: dist[last][j])
        order.append(nxt)
        unvisited.remove(nxt)
    return order

def route_cost(order: List[int], dist: List[List[float]]) -> float:
    return sum(dist[order[i]][order[i + 1]] for i in range(len(order) - 1))

def two_opt(order: List[int], dist: List[List[float]], max_passes: int = 10) -> List[int]:
    best = order[:]
    best_cost = route_cost(best, dist)
    n = len(order)
    improved = True
    passes = 0
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for i in range(0, n - 3):
            for k in range(i + 2, n - 1):
                new_order = best[:i + 1] + best[i + 1:k + 1][::-1] + best[k + 1:]
                new_cost = route_cost(new_order, dist)
                if new_cost + 1e-9 < best_cost:
                    best = new_order
                    best_cost = new_cost
                    improved = True
    return best

# --- Helpers (No changes here) ---
def _extract_all_pois(itinerary_data: Dict) -> List[Dict]:
    all_pois = []
    for _, activities in itinerary_data.items():
        if isinstance(activities, list):
            for poi in activities:
                loc = poi.get("coordinates") or poi.get("location")
                if loc and "lat" in loc and "lng" in loc:
                    poi = deepcopy(poi)
                    poi["location"] = {"lat": float(loc["lat"]), "lng": float(loc["lng"])}
                    all_pois.append(poi)
    return all_pois

def _choose_start_index(coords: List[Tuple[float, float]]) -> int:
    n = len(coords)
    best_idx, best_avg = 0, float("inf")
    for i in range(n):
        avg = sum(haversine_km(coords[i], coords[j]) for j in range(n) if j != i) / (n - 1 if n > 1 else 1)
        if avg < best_avg:
            best_idx, best_avg = i, avg
    return best_idx

# In proximity_optimizer.py, replace the existing function

# 🔽 REVISED BUCKETING FUNCTION 🔽
def _bucket_route_into_days_with_constraints(
    order: List[int],
    pois: List[Dict],
    dist: List[List[float]],
    daily_time_budget: float,
    max_daily_travel_hours: float
) -> List[List[int]]:
    """Splits the optimized route into days respecting activity, travel, AND intensity constraints."""
    if not order:
        return []

    day_buckets = []
    current_day_indices = []
    activity_time = 0.0
    travel_time = 0.0
    high_intensity_count = 0 # NEW: Track high-intensity activities for the current day
    avg_speed_kmh = 20.0

    for i, poi_idx in enumerate(order):
        poi = pois[poi_idx]
        poi_duration = poi.get("estimated_visit_duration", 1.5)
        poi_intensity = poi.get("intensity", "medium")
        
        time_to_travel = 0.0
        if i > 0 and current_day_indices:
            prev_poi_idx = current_day_indices[-1]
            distance_km = dist[prev_poi_idx][poi_idx]
            time_to_travel = distance_km / avg_speed_kmh
        
        # --- NEW: Pacing Rule Check ---
        # Can we add this POI without breaking the intensity rule?
        can_add_high_intensity = not (poi_intensity == 'high' and high_intensity_count >= 1)

        # --- MODIFIED: Budget Check Logic now includes the pacing rule ---
        exceeds_activity_budget = (activity_time + poi_duration > daily_time_budget)
        exceeds_travel_budget = (travel_time + time_to_travel > max_daily_travel_hours)

        if exceeds_activity_budget or exceeds_travel_budget or not can_add_high_intensity:
            # Current day is full or cannot accommodate this POI. Finalize it.
            day_buckets.append(current_day_indices)
            
            # Start a new day with the current POI
            current_day_indices = [poi_idx]
            activity_time = poi_duration
            travel_time = 0.0
            high_intensity_count = 1 if poi_intensity == 'high' else 0 # Reset count for new day
        else:
            # Add POI to the current day and update budgets
            current_day_indices.append(poi_idx)
            activity_time += poi_duration
            travel_time += time_to_travel
            if poi_intensity == 'high':
                high_intensity_count += 1

    # Add the last day to the buckets
    if current_day_indices:
        day_buckets.append(current_day_indices)
        
    return day_buckets
# --- Main entry ---
# ## MODIFIED: The main function now accepts budget parameters
def optimize_itinerary_by_proximity(
    user_id: str,
    trip_id: str,
    daily_time_budget: float = 7.5,
    max_daily_travel_hours: float = 2.0,
    backup_original: bool = True
) -> Dict:
    doc_ref = itinerary_doc(user_id, trip_id)
    snap = doc_ref.get()
    doc = snap.to_dict() if snap.exists else None

    if not doc:
        return {}

    itinerary_data = doc.get("itinerary", {})
    if not itinerary_data:
        return {}

    pois = _extract_all_pois(itinerary_data)
    if not pois:
        return {}

    coords = [(p["location"]["lat"], p["location"]["lng"]) for p in pois]
    dist = build_distance_matrix(coords)
    
    start_idx = _choose_start_index(coords)
    nn_order = nearest_neighbor_order(dist, start_idx=start_idx)
    best_order = two_opt(nn_order, dist)

    # ## MODIFIED: Call the new bucketing function instead of the old split
    index_days = _bucket_route_into_days_with_constraints(
        best_order, pois, dist, daily_time_budget, max_daily_travel_hours
    )

    # Build new itinerary mapping from the smart buckets
    new_itinerary = {}
    for i, idxs in enumerate(index_days):
        day_name = f"Day {i+1}"
        new_itinerary[day_name] = [pois[j] for j in idxs]

    if backup_original and not doc.get("itinerary_original_backup"):
        doc_ref.update({"itinerary_original_backup": itinerary_data})

    doc_ref.update({"itinerary": new_itinerary})
    print(f"✅ Itinerary optimized with time constraints for user={user_id}, trip={trip_id}")
    return new_itinerary

# Optional: run local test
if __name__ == "__main__":
    # ... (test code remains the same)
    print("🔄 Running global proximity optimization test...")
    _user = "user_123"
    _trip = "07c2f0d4-f687-462a-a300-793353548adc"
    # ## MODIFIED: Test call now includes budgets
    res = optimize_itinerary_by_proximity(_user, _trip, daily_time_budget=8.0, max_daily_travel_hours=2.5)
    if res:
        for d, activities in res.items():
            print(d, "→", [p["name"] for p in activities])