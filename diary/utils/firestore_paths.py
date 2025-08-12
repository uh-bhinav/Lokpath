from diary.firebase.firebase_config import db

# Centralized Firestore path helpers for unified structure
# Canonical: /users/{uid}/itineraries/{trip_id}/photos/{photo_id}

def user_doc(user_id: str):
    return db.collection("users").document(user_id)


def itineraries_col(user_id: str):
    return user_doc(user_id).collection("itineraries")


def itinerary_doc(user_id: str, trip_id: str):
    return itineraries_col(user_id).document(trip_id)


def photos_col(user_id: str, trip_id: str):
    return itinerary_doc(user_id, trip_id).collection("photos")

