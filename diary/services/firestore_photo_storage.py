from diary.utils.firestore_paths import photos_col

def save_photo_to_firestore(user_id, trip_id, photo_id, photo_data):
    """
    Save photo metadata to Firestore
    
    Structure: /diary/{user_id}/itineraries/{trip_id}/photos/{photo_id}
    """
    try:
        doc_ref = photos_col(user_id, trip_id).document(photo_id)
        doc_ref.set(photo_data)
        print(f"✅ Photo metadata saved to Firestore: {photo_id}")
        return True
    except Exception as e:
        print(f"❌ Firestore save error: {e}")
        return False

def get_photos_from_firestore(user_id, trip_id):
    """
    Retrieve all photos for a trip from Firestore
    """
    try:
        photos_ref = photos_col(user_id, trip_id)
        docs = photos_ref.order_by("timestamp").stream()
        photos = []
        for doc in docs:
            photo_data = doc.to_dict()
            photo_data["photo_id"] = doc.id
            photos.append(photo_data)
        return photos
    except Exception as e:
        print(f"❌ Firestore fetch error: {e}")
        return []

def delete_photo_from_firestore(user_id, trip_id, photo_id):
    """
    Delete photo metadata from Firestore
    """
    try:
        doc_ref = photos_col(user_id, trip_id).document(photo_id)
        doc_ref.delete()
        print(f"✅ Photo metadata deleted from Firestore: {photo_id}")
        return True
    except Exception as e:
        print(f"❌ Firestore delete error: {e}")
        return False
