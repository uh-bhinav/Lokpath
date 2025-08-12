import math
import sys
import os
from typing import List, Dict, Tuple
from copy import deepcopy

# ✅ Fix Python import path to support running as script
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from diary.utils.firestore_paths import itinerary_doc


# -----------------------------
# Distance utilities
# -----------------------------
def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371.0
    lat1, lon1 = a
    lat2, lon2 = b
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    la1 = math.radians(lat1)
    la2 = math.radians(lat2)

    h = (math.sin(d_lat / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin(d_lon / 2) ** 2)
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


# -----------------------------
# Global route: NN + 2-Opt
# -----------------------------
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
    """Simple 2-opt to improve NN path; no wrap (not a cycle)."""
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
        # if no improvement in this pass, we stop
    return best


# -----------------------------
# Helpers
# -----------------------------
def _extract_all_pois(itinerary_data: Dict) -> List[Dict]:
    """Flatten days -> list of POI dicts that include a normalized 'location'."""
    all_pois = []
    for _, activities in itinerary_data.items():
        if isinstance(activities, list):
            for poi in activities:
                loc = poi.get("coordinates") or poi.get("location")
                if loc and "lat" in loc and "lng" in loc:
                    # normalize into poi["location"]
                    poi = deepcopy(poi)
                    poi["location"] = {"lat": float(loc["lat"]), "lng": float(loc["lng"])}
                    all_pois.append(poi)
    return all_pois


def _choose_start_index(coords: List[Tuple[float, float]]) -> int:
    """Heuristic: start near the point with min average distance to others (central-ish)."""
    n = len(coords)
    best_idx, best_avg = 0, float("inf")
    for i in range(n):
        avg = sum(haversine_km(coords[i], coords[j]) for j in range(n) if j != i) / (n - 1 if n > 1 else 1)
        if avg < best_avg:
            best_idx, best_avg = i, avg
    return best_idx


def _split_into_days(order: List[int], num_days: int) -> List[List[int]]:
    """Balanced split: sizes differ by at most 1."""
    n = len(order)
    base = n // num_days
    remainder = n % num_days
    sizes = [base + 1 if i < remainder else base for i in range(num_days)]
    out, idx = [], 0
    for s in sizes:
        out.append(order[idx: idx + s])
        idx += s
    return out


# -----------------------------
# Main entry
# -----------------------------
def optimize_itinerary_by_proximity(user_id: str, trip_id: str, backup_original: bool = True) -> Dict:
    """
    Global proximity optimization:
      1) Flatten all POIs (ignore current Day buckets)
      2) Build a single best path (NN + 2-Opt)
      3) Split back into the same number of days (balanced)
      4) Overwrite itinerary in Firestore (optionally store backup once)
    """
    doc_ref = itinerary_doc(user_id, trip_id)
    snap = doc_ref.get()
    doc = snap.to_dict() if snap.exists else None

    if not doc:
        print("❌ No itinerary document found.")
        return {}

    itinerary_data = doc.get("itinerary", {})
    if not itinerary_data:
        print("❌ 'itinerary' field is missing.")
        return {}

    num_days = len(itinerary_data)
    pois = _extract_all_pois(itinerary_data)

    if not pois:
        print("❌ No POIs to optimize.")
        return {}

    # Coordinates & distance matrix
    coords = [(p["location"]["lat"], p["location"]["lng"]) for p in pois]
    dist = build_distance_matrix(coords)

    # Build global route
    start_idx = _choose_start_index(coords)
    nn_order = nearest_neighbor_order(dist, start_idx=start_idx)
    best_order = two_opt(nn_order, dist, max_passes=12)

    # Split route back into days
    index_days = _split_into_days(best_order, num_days)

    # Build new itinerary mapping
    new_itinerary = {}
    day_names = sorted(list(itinerary_data.keys()), key=lambda s: (
        int(s.split()[-1]) if s.lower().startswith("day") and s.split()[-1].isdigit() else 9999, s
    ))
    if len(day_names) != num_days:
        # fallback to "Day 1..N" if keys aren't consistent
        day_names = [f"Day {i+1}" for i in range(num_days)]

    for i, idxs in enumerate(index_days):
        new_itinerary[day_names[i]] = [pois[j] for j in idxs]

    # Optional: keep a one-time backup
    if backup_original and not doc.get("itinerary_original_backup"):
        doc_ref.update({"itinerary_original_backup": itinerary_data})

    # Update Firestore
    doc_ref.update({"itinerary": new_itinerary})
    print(f"✅ Itinerary globally optimized for user={user_id}, trip={trip_id}")
    return new_itinerary


# Optional: run local test
if __name__ == "__main__":
    print("🔄 Running global proximity optimization test...")
    _user = "user_123"
    _trip = "07c2f0d4-f687-462a-a300-793353548adc"
    res = optimize_itinerary_by_proximity(_user, _trip)
    if res:
        for d, activities in res.items():
            print(d, "→", [p["name"] for p in activities])
