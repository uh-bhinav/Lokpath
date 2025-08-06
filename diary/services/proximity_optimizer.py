import math
import sys
import os
from collections import defaultdict
from sklearn.cluster import KMeans

# ✅ Fix Python import path to support running as script
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from diary.firebase.firebase_config import db

# ✅ Sample data for development/testing
def _get_sample_optimized_itinerary():
    """Returns sample optimized itinerary for development when Firebase is not available"""
    return {
        "Day 1": [
            {"name": "Central Park", "location": {"lat": 40.7829, "lng": -73.9654}},
            {"name": "Times Square", "location": {"lat": 40.7580, "lng": -73.9855}},
            {"name": "Empire State Building", "location": {"lat": 40.7484, "lng": -73.9857}}
        ],
        "Day 2": [
            {"name": "Brooklyn Bridge", "location": {"lat": 40.7061, "lng": -73.9969}},
            {"name": "One World Trade Center", "location": {"lat": 40.7127, "lng": -74.0134}},
            {"name": "Statue of Liberty", "location": {"lat": 40.6892, "lng": -74.0445}}
        ]
    }


# ✅ Haversine distance between two coordinates
def haversine_distance(coord1, coord2):
    R = 6371  # Earth radius in km
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = math.sin(d_lat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ✅ Greedy TSP: reorder POIs by nearest neighbor
def order_by_proximity(pois):
    if not pois:
        return []
    
    start = pois[0]
    ordered = [start]
    unvisited = pois[1:]

    while unvisited:
        last = ordered[-1]
        nearest = min(unvisited, key=lambda poi: haversine_distance(
            (last['location']['lat'], last['location']['lng']),
            (poi['location']['lat'], poi['location']['lng'])
        ))
        ordered.append(nearest)
        unvisited.remove(nearest)

    return ordered


# ✅ Main function: fetch itinerary, cluster POIs, reorder, and update Firestore
def optimize_itinerary_by_proximity(user_id, trip_id, num_days=None):
    try:
        # Handle mock Firebase case
        if hasattr(db, '_mock_name'):
            print("⚠️ Using mock Firebase - returning sample optimized data")
            return _get_sample_optimized_itinerary()

        doc_ref = db.collection("diary").document(user_id).collection("itineraries").document(trip_id)
        itinerary_doc_snapshot = doc_ref.get()
        
        if not itinerary_doc_snapshot.exists:
            print(f"❌ No itinerary document found for user: {user_id}, trip: {trip_id}")
            return None
            
        itinerary_doc = itinerary_doc_snapshot.to_dict()

        if not itinerary_doc:
            print("❌ Itinerary document is empty.")
            return None

        itinerary_data = itinerary_doc.get("itinerary", {})
        if not itinerary_data:
            print("❌ 'itinerary' field is missing.")
            return None

        all_pois = []

        # ✅ Extract POIs and standardize coordinate format
        for day_key, activities in itinerary_data.items():
            if isinstance(activities, list):
                for poi in activities:
                    location = poi.get("coordinates") or poi.get("location")
                    if location and "lat" in location and "lng" in location:
                        poi["location"] = {
                            "lat": location["lat"],
                            "lng": location["lng"]
                        }
                        # Fix any malformed photo URLs
                        if "photo_url" in poi and poi["photo_url"]:
                            poi["photo_url"] = poi["photo_url"].replace("\n", "").replace(" ", "")
                        all_pois.append(poi)

    except Exception as e:
        print(f"❌ Error accessing Firestore: {e}")
        return None

    if not all_pois:
        print("❌ No POIs to optimize.")
        return None

    coords = [(poi["location"]["lat"], poi["location"]["lng"]) for poi in all_pois]
    num_clusters = num_days or len(itinerary_data)

    # ✅ Cluster POIs using K-Means
    kmeans = KMeans(n_clusters=num_clusters, random_state=42)
    labels = kmeans.fit_predict(coords)

    clustered = defaultdict(list)
    for poi, label in zip(all_pois, labels):
        clustered[label].append(poi)

    # ✅ Reorder POIs within each cluster and build new itinerary
    new_itinerary = {}
    for i, cluster_id in enumerate(sorted(clustered.keys()), 1):
        ordered_cluster = order_by_proximity(clustered[cluster_id])
        new_itinerary[f"Day {i}"] = ordered_cluster

    # ✅ Update Firestore
    doc_ref.update({"itinerary": new_itinerary})
    print(f"✅ Itinerary updated successfully for user: {user_id}, trip: {trip_id}")
    return new_itinerary


# ✅ Optional: Test block for running standalone
if __name__ == "__main__":
    print("🔄 Running proximity optimization test...")

    user_id = "user_123"
    trip_id = "07c2f0d4-f687-462a-a300-793353548adc"

    result = optimize_itinerary_by_proximity(user_id, trip_id)

    if result:
        print("🎯 Optimized Itinerary:")
        for day, pois in result.items():
            print(f"{day}: {[poi['name'] for poi in pois]}")
    else:
        print("⚠️ Optimization failed or no POIs found.")
