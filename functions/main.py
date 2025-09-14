# functions/main.py

import os
import datetime
import tempfile
from firebase_functions import firestore_fn, storage_fn, scheduler_fn
from firebase_admin import initialize_app, storage, firestore, messaging
from PIL import Image
import pillow_heif
from google.cloud import vision
from firebase_functions import https_fn, options
# from sentence_transformers import SentenceTransformer
# from sklearn.metrics.pairwise import cosine_similarity
import json
# from transformers import pipeline

# Initialize Firebase Admin SDK
# This is done once when the function instance starts up.
initialize_app()
pillow_heif.register_heif_opener()

options.set_global_options(region=options.SupportedRegion.ASIA_SOUTH1)

# Define the thumbnail sizes you want to create
THUMBNAIL_SIZES = {
    "small": (200, 200),
    "medium": (800, 800)
}

@storage_fn.on_object_finalized()
def process_uploaded_image(event: storage_fn.CloudEvent) -> None:
    """
    Triggered when a new file is uploaded to Cloud Storage.
    It converts HEIC files, creates thumbnails, and updates Firestore.
    """
    bucket_name = event.data.bucket
    file_path = event.data.name
    content_type = event.data.content_type

    # --- 1. Exit if the file is not an image or is already a thumbnail ---
    if not content_type or not content_type.startswith("image/"):
        print(f"File {file_path} is not an image. Skipping.")
        return
    if "thumbnails/" in file_path:
        print(f"File {file_path} is already a thumbnail. Skipping.")
        return

    bucket = storage.bucket(bucket_name)
    blob = bucket.blob(file_path)

    # --- 2. Download the original image to a temporary location ---
    # Cloud Functions provide a temporary directory for this kind of work.
    _, temp_local_path = tempfile.mkstemp(dir=tempfile.gettempdir())
    blob.download_to_filename(temp_local_path)
    print(f"Image {file_path} downloaded to {temp_local_path}.")

    try:
        # --- 3. Handle HEIC to JPEG conversion ---
        # This reuses the logic from your diary_photo_uploader.py
        image_path_for_processing = temp_local_path
        file_extension = ".jpeg"
        if content_type in ["image/heic", "image/heif"]:
            print(f"Converting HEIC file: {file_path}")
            # The new file will have a .jpeg extension
            jpeg_path = os.path.splitext(temp_local_path)[0] + file_extension
            with Image.open(temp_local_path) as img:
                img.save(jpeg_path, format="JPEG")
            image_path_for_processing = jpeg_path

        # --- 4. Create and upload thumbnails ---
        thumbnail_urls = {}
        with Image.open(image_path_for_processing) as img:
            for size_name, dimensions in THUMBNAIL_SIZES.items():
                img.thumbnail(dimensions)
                
                # Define the path for the new thumbnail in the bucket
                thumbnail_path = f"thumbnails/{os.path.splitext(file_path)[0]}_{size_name}{file_extension}"
                thumb_blob = bucket.blob(thumbnail_path)
                
                # Save the resized image to a temporary file, then upload
                _, temp_thumb_path = tempfile.mkstemp(suffix=file_extension)
                img.save(temp_thumb_path)
                
                thumb_blob.upload_from_filename(temp_thumb_path)
                thumb_blob.make_public()
                thumbnail_urls[f"url_{size_name}"] = thumb_blob.public_url
                print(f"Generated and uploaded thumbnail: {thumbnail_path}")

                os.remove(temp_thumb_path) # Clean up temp thumbnail

        # --- 5. Update the corresponding Firestore Document ---
        # Find which document this image belongs to by parsing the file path.
        update_firestore_with_thumbnails(file_path, thumbnail_urls)

    finally:
        # --- 6. Clean up the original downloaded file ---
        os.remove(temp_local_path)


def update_firestore_with_thumbnails(original_path: str, thumbnail_urls: dict):
    """
    Finds the correct Firestore document based on the image path and updates it
    with the new thumbnail URLs.
    """
    db = firestore.client()
    parts = original_path.split('/')
    
    # This logic is based on YOUR file structure from app.py: uploads/{type}/{sessionId_or_userId}/{...}
    # For example: "uploads/diary_photos/user123/trip456/photo789.jpg"
    # or "uploads/gems/sessionABC/image.jpg"
    
    upload_type = parts[1] if len(parts) > 1 else None
    
    # Logic for Diary Photos
    if upload_type == "diary_photos":
        if len(parts) >= 5:
            user_id, trip_id, file_name = parts[2], parts[3], parts[4]
            photo_id = os.path.splitext(file_name)[0]
            # Path based on your firestore_paths.py
            doc_ref = db.collection("users").document(user_id).collection("itineraries").document(trip_id).collection("photos").document(photo_id)
            doc_ref.set({"thumbnails": thumbnail_urls}, merge=True)
            print(f"Updated diary photo doc: {doc_ref.path}")

    # Logic for Hidden Gem or Artisan Submissions
    elif upload_type in ["gems", "artisans"]:
        # The URL is stored in a temporary submission_sessions document.
        # We find the session document that contains the original image's public URL.
        original_public_url = storage.bucket().blob(original_path).public_url
        
        query = db.collection("submission_sessions").where("image_urls", "array_contains", original_public_url)
        docs = list(query.stream())
        
        if docs:
            session_ref = docs[0].reference
            
            # Add the thumbnails to a new 'thumbnails' map in the session
            # And add the specific URL to a map of original_url -> thumbnails
            update_data = {
                f"thumbnail_map.{original_public_url.replace('.', '_')}": thumbnail_urls
            }
            session_ref.set(update_data, merge=True)
            print(f"Updated submission session doc: {session_ref.path}")
        else:
            print(f"Could not find a submission session for image: {original_path}")


@storage_fn.on_object_finalized()
def moderate_uploaded_image(event: storage_fn.CloudEvent) -> None:
    """
    Analyzes uploaded images for NSFW content using the Cloud Vision API
    and flags them in Firestore if necessary.
    """
    bucket_name = event.data.bucket
    file_path = event.data.name
    content_type = event.data.content_type

    if not content_type or not content_type.startswith("image/"):
        print(f"File {file_path} is not an image. Skipping moderation.")
        return
    if "thumbnails/" in file_path:
        print(f"File {file_path} is a thumbnail. Skipping moderation.")
        return

    gcs_uri = f"gs://{bucket_name}/{file_path}"
    
    try:
        print(f"Analyzing {gcs_uri} for safe search...")
        response = vision_client.safe_search_detection(image=vision.Image(source=vision.ImageSource(gcs_image_uri=gcs_uri)))
        safe_search = response.safe_search_annotation

        # Define likelihood levels that we consider unsafe
        unsafe_levels = (vision.Likelihood.LIKELY, vision.Likelihood.VERY_LIKELY)

        is_unsafe = False
        reasons = []
        if safe_search.adult in unsafe_levels:
            is_unsafe = True
            reasons.append("ADULT")
        if safe_search.violence in unsafe_levels:
            is_unsafe = True
            reasons.append("VIOLENCE")
        
        moderation_status = "REJECTED" if is_unsafe else "APPROVED"
        
        print(f"Moderation result for {gcs_uri}: {moderation_status}. Reasons: {reasons if reasons else 'None'}")

        # Update the corresponding Firestore document with the moderation result
        _update_firestore_with_moderation_status(file_path, moderation_status, reasons)

    except Exception as e:
        print(f"Error during content moderation for {gcs_uri}: {e}")

def _update_firestore_with_moderation_status(original_path: str, status: str, reasons: list):
    """
    Finds the correct Firestore document and updates it with the moderation status.
    """
    db = firestore.client()
    parts = original_path.split('/')
    
    # This logic mirrors the thumbnail update function to find the right document
    upload_type = None
    if len(parts) > 1 and parts[0] == "uploads": # Structure from app.py
        upload_type = parts[1]

    doc_ref = None
    
    if upload_type == "diary_photos" and len(parts) >= 5:
        user_id, trip_id, file_name = parts[2], parts[3], parts[4]
        photo_id = os.path.splitext(file_name)[0]
        doc_ref = db.collection("users").document(user_id).collection("itineraries").document(trip_id).collection("photos").document(photo_id)
    
    elif upload_type in ["gems", "artisans"]:
        public_url = storage.bucket().blob(original_path).public_url
        query = db.collection("submission_sessions").where("image_urls", "array_contains", public_url)
        docs = list(query.stream())
        if docs:
            doc_ref = docs[0].reference

    if doc_ref:
        update_data = {
            "moderation_status": status,
            "moderation_reasons": reasons
        }
        doc_ref.set(update_data, merge=True)
        print(f"Updated moderation status for doc: {doc_ref.path}")
    else:
        print(f"Could not find a Firestore document to update for image: {original_path}")



@firestore_fn.on_document_written(document="guides/{guideId}/reviews/{reviewId}")
def update_guide_rating(event: firestore_fn.Event[firestore_fn.Change]) -> None:
    """
    Triggered when a new review is written for a guide. It recalculates the
    guide's average rating and total review count and updates the main guide document.
    """
    # Get the guideId from the wildcard in the path of the trigger
    guide_id = event.params.get("guideId")
    if not guide_id:
        print("No guideId found in event parameters. Exiting.")
        return

    db = firestore.client()
    
    # Get a reference to the main guide document.
    # This path matches your Firestore structure for a guide's profile.
    guide_ref = db.collection("guides").document(guide_id)
    
    # Get a reference to the reviews sub-collection for that guide.
    reviews_ref = guide_ref.collection("reviews")
    
    # --- Recalculation Logic ---
    # This is the same logic you have in your Flask route, but now it runs in the background.
    all_reviews = reviews_ref.stream()

    total_rating = 0
    num_reviews = 0
    
    for review in all_reviews:
        rating = review.to_dict().get("rating", 0)
        # Ensure rating is a valid number before adding
        if isinstance(rating, (int, float)):
            total_rating += rating
            num_reviews += 1
        
    # Calculate the new average rating, avoiding division by zero
    new_average_rating = round(total_rating / num_reviews, 1) if num_reviews > 0 else 0.0

    # --- Update the Main Guide Document ---
    # This updates the 'average_rating' and 'total_reviews' fields on the guide's profile.
    guide_ref.update({
        "average_rating": new_average_rating,
        "total_reviews": num_reviews
    })

    print(f"Guide rating updated for {guide_id}. New Average: {new_average_rating}, Total Reviews: {num_reviews}")


@firestore_fn.on_document_created(document="bookings/{bookingId}")
def assign_guide_to_booking(event: firestore_fn.Event[firestore_fn.Change]) -> None:
    booking_ref = event.reference
    booking_data = event.data.to_dict()
    if booking_data.get("status") != "pending_assignment": return
    potential_guides = booking_data.get("potential_guides", [])
    if not potential_guides:
        booking_ref.update({"status": "failed", "failure_reason": "No potential guides found"})
        return
    assigned_guide_uid = potential_guides[0]
    assignment_time = datetime.datetime.now(datetime.timezone.utc)
    deadline = assignment_time + datetime.timedelta(minutes=60)
    booking_ref.update({
        "status": "pending_acceptance",
        "assigned_guide_uid": assigned_guide_uid,
        "guide_response_deadline": deadline.isoformat(),
        "reminders_sent": {"thirty_minute": False, "five_minute": False},
        "assignment_history": firestore.ArrayUnion([{"guide_uid": assigned_guide_uid, "assigned_at": assignment_time.isoformat(), "status": "pending"}])
    })
    # The print/log statement for notification is now handled by send_booking_notifications
    print(f"Assigned guide {assigned_guide_uid} to booking {booking_ref.id}.")


@firestore_fn.on_document_updated(document="bookings/{bookingId}")
def handle_booking_rejection(event: firestore_fn.Event[firestore_fn.Change]) -> None:
    # This function's code remains the same, but no longer needs to print notifications...
    before_data, after_data = event.data.before.to_dict(), event.data.after.to_dict()
    booking_ref = event.reference
    is_rejection = before_data.get("status") == "pending_acceptance" and after_data.get("status") == "rejected_by_guide"
    is_timeout = before_data.get("status") == "pending_acceptance" and after_data.get("status") == "timed_out"
    if not (is_rejection or is_timeout): return
    rejected_guide_uid = before_data.get("assigned_guide_uid")
    potential_guides = after_data.get("potential_guides", [])
    try:
        rejected_index = potential_guides.index(rejected_guide_uid)
    except ValueError:
        booking_ref.update({"status": "failed", "failure_reason": "Internal error: guide list mismatch."})
        return
    next_guide_index = rejected_index + 1
    if next_guide_index < len(potential_guides):
        next_guide_uid = potential_guides[next_guide_index]
        assignment_time = datetime.datetime.now(datetime.timezone.utc)
        deadline = assignment_time + datetime.timedelta(minutes=60)
        booking_ref.update({
            "status": "pending_acceptance",
            "assigned_guide_uid": next_guide_uid,
            "guide_response_deadline": deadline.isoformat(),
            "reminders_sent": {"thirty_minute": False, "five_minute": False},
            "assignment_history": firestore.ArrayUnion([{"guide_uid": next_guide_uid, "assigned_at": assignment_time.isoformat(), "status": "pending"}])
        })
    else:
        booking_ref.update({"status": "failed", "failure_reason": "All available guides rejected or timed out."})


@scheduler_fn.on_schedule(schedule="every 5 minutes")
def check_booking_status(event: scheduler_fn.ScheduledEvent) -> None:
    # This function's code remains the same, but no longer needs to print notifications...
    db = firestore.client()
    now = datetime.datetime.now(datetime.timezone.utc)
    query = db.collection("bookings").where("status", "==", "pending_acceptance")
    pending_bookings = query.stream()
    for doc in pending_bookings:
        booking_data = doc.to_dict()
        deadline_str = booking_data.get("guide_response_deadline")
        if not deadline_str: continue
        deadline = datetime.datetime.fromisoformat(deadline_str)
        minutes_left = (deadline - now).total_seconds() / 60
        if minutes_left <= 0:
            doc.reference.update({"status": "timed_out"})
            continue
        reminders = booking_data.get("reminders_sent", {})
        if 25 < minutes_left <= 30 and not reminders.get("thirty_minute"):
            doc.reference.update({"reminders_sent.thirty_minute": True})
            # Send actual reminder
            send_fcm_notification(booking_data.get("assigned_guide_uid"), "Trip Request Reminder", "You have 30 minutes to respond.")
        elif 1 < minutes_left <= 5 and not reminders.get("five_minute"):
            doc.reference.update({"reminders_sent.five_minute": True})
            # Send actual reminder
            send_fcm_notification(booking_data.get("assigned_guide_uid"), "Final Trip Reminder", "Your trip request will expire in 5 minutes.")



def send_fcm_notification(user_id: str, title: str, body: str, data: dict = None):
    """
    Fetches a user's FCM tokens from Firestore and sends a push notification.
    """
    db = firestore.client()
    tokens_ref = db.collection("users").document(user_id).collection("device_tokens")
    tokens_docs = tokens_ref.stream()
    
    tokens = [doc.to_dict().get("token") for doc in tokens_docs if doc.to_dict().get("token")]

    if not tokens:
        print(f"No device tokens found for user {user_id}. Cannot send notification.")
        return

    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data or {},
        tokens=tokens,
    )

    try:
        response = messaging.send_multicast(message)
        print(f"Successfully sent {response.success_count} notifications for user {user_id}.")
        if response.failure_count > 0:
            # Optional: Add logic here to clean up invalid tokens
            print(f"Failed to send {response.failure_count} notifications for user {user_id}.")
    except Exception as e:
        print(f"Error sending FCM notification to user {user_id}: {e}")


# --- [NEW] Centralized Notification Handler Function ---
@firestore_fn.on_document_updated(document="bookings/{bookingId}")
def send_booking_notifications(event: firestore_fn.Event[firestore_fn.Change]) -> None:
    """
    Listens for booking status changes and sends relevant push notifications.
    """
    before_data = event.data.before.to_dict()
    after_data = event.data.after.to_dict()

    status_before = before_data.get("status")
    status_after = after_data.get("status")
    
    if status_before == status_after:
        return # No status change, no notification needed

    tourist_uid = after_data.get("tourist_uid")
    guide_uid = after_data.get("assigned_guide_uid")
    booking_id = event.params.get("bookingId")
    data_payload = {"booking_id": booking_id, "click_action": "FLUTTER_NOTIFICATION_CLICK"}

    # Case 1: New guide assignment (or re-assignment)
    if status_after == "pending_acceptance" and guide_uid:
        send_fcm_notification(
            user_id=guide_uid,
            title="New Trip Request!",
            body="A new trip is available. Respond within 60 minutes to accept.",
            data=data_payload
        )

    # Case 2: Booking was accepted by a guide
    elif status_after == "accepted" and tourist_uid:
        send_fcm_notification(
            user_id=tourist_uid,
            title="Your Guide is Confirmed!",
            body=f"Your booking {booking_id} has been accepted.",
            data=data_payload
        )

    # Case 3: Booking failed (no guides available)
    elif status_after == "failed" and tourist_uid:
        send_fcm_notification(
            user_id=tourist_uid,
            title="Could Not Find a Guide",
            body=f"We're sorry, we couldn't find an available guide for your trip.",
            data=data_payload
        )
    
    # Case 4: Booking was cancelled by the tourist
    elif status_after == "cancelled_by_tourist" and guide_uid:
         send_fcm_notification(
            user_id=guide_uid,
            title="Booking Cancelled",
            body=f"The booking {booking_id} was cancelled by the tourist.",
            data=data_payload
        )

# --- START: Add the extracttags function ---

# --- 1. Models are initialized to None to ensure fast deployment. ---
model_extract_tags = None
classifier_tag_reviews = None
LABEL_EMBEDDINGS = None
print("✅ Global scope loaded instantly.")

LABELS = [
    "romantic", "adventurous", "family-friendly", "spiritual", "sunset", "nature",
    "photogenic", "historical", "cultural", "peaceful", "crowded", "quiet",
    "trek", "local food", "viewpoint"
]

@https_fn.on_request(memory=options.MemoryOption.GB_2)
def extracttags(req: https_fn.Request) -> https_fn.Response:
    """HTTP Cloud Function to extract tags using sentence similarity."""
    global model_extract_tags, LABEL_EMBEDDINGS

    headers = {"Access-Control-Allow-Origin": "*"}
    if req.method == "OPTIONS":
        cors_headers = {"Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "3600"}
        return https_fn.Response("", status=204, headers={**headers, **cors_headers})

    try:
        # --- 2. Inside the function, we check if the model is loaded. ---
        if model_extract_tags is None:
            print("Cold start: Loading SentenceTransformer model...")
            # --- 3. If not, we load it once (the "cold start"). ---
            from sentence_transformers import SentenceTransformer
            from sklearn.metrics.pairwise import cosine_similarity
            model_extract_tags = SentenceTransformer('all-MiniLM-L6-v2')
            LABEL_EMBEDDINGS = model_extract_tags.encode(LABELS)
            print("✅ SentenceTransformer model loaded successfully.")

        if req.method != 'POST':
            return https_fn.Response("Method not allowed.", status=405, headers=headers)

        data = req.get_json()
        description = data.get('description')
        if not description:
            return https_fn.Response("Missing 'description' in request body.", status=400, headers=headers)

        desc_embedding = model_extract_tags.encode([description])
        similarities = cosine_similarity(desc_embedding, LABEL_EMBEDDINGS)[0]
        
        tag_scores = sorted(list(zip(LABELS, similarities)), key=lambda x: x[1], reverse=True)
        
        # --- START: New and improved selection logic ---
        threshold = 0.4
        top_n = 3
        
        # 1. Select all tags that are above the confidence threshold
        selected_tags = [label for label, score in tag_scores if score >= threshold]
        
        # 2. If we still don't have enough tags, fill with the next best ones
        if len(selected_tags) < top_n:
            # Get the remaining tags that weren't selected
            remaining_tags = [label for label, score in tag_scores if label not in selected_tags]
            # Add tags until we reach top_n
            needed = top_n - len(selected_tags)
            selected_tags.extend(remaining_tags[:needed])
        # --- END: New logic ---

        return https_fn.Response(json.dumps(selected_tags[:top_n]), status=200, headers=headers, content_type="application/json")


    except Exception as e:
        print(f"ERROR in extracttags: {e}")
        return https_fn.Response("An error occurred.", status=500, headers=headers)

@https_fn.on_request(memory=options.MemoryOption.GB_2)
def tagplacewithreviews(req: https_fn.Request) -> https_fn.Response:
    """HTTP Cloud Function to tag a place based on a list of reviews."""
    global classifier_tag_reviews

    headers = {"Access-Control-Allow-Origin": "*"}
    if req.method == "OPTIONS":
        cors_headers = {"Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "3600"}
        return https_fn.Response("", status=204, headers={**headers, **cors_headers})

    try:
        # --- 2. We do the same "lazy load" for the second model. ---
        if classifier_tag_reviews is None:
            print("Cold start: Loading zero-shot classification model...")
            from transformers import pipeline
            classifier_tag_reviews = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=-1
            )
            print("✅ Zero-shot classification model loaded successfully.")

        if req.method != 'POST':
            return https_fn.Response("Method not allowed.", status=405, headers=headers)
            
        data = req.get_json()
        reviews = data.get('reviews')
        if not isinstance(reviews, list):
            return https_fn.Response("Missing 'reviews' list in request body.", status=400, headers=headers)

        tag_count = {}
        for review in reviews:
            if not review: continue
            result = classifier_tag_reviews(review, LABELS, multi_label=True)
            for label, score in zip(result["labels"], result["scores"]):
                if score >= 0.7:
                    tag_count[label] = tag_count.get(label, 0) + 1
        
        final_tags = [tag for tag, count in tag_count.items() if count >= 1]
        
        response_data = {"tags": final_tags, "intensity": "medium"}
        return https_fn.Response(json.dumps(response_data), status=200, headers=headers, content_type="application/json")

    except Exception as e:
        print(f"ERROR in tagplacewithreviews: {e}")
        return https_fn.Response("An error occurred.", status=500, headers=headers)


"""print("✅ Dummy main.py loaded instantly.")

@https_fn.on_request(memory=options.MemoryOption.GB_2)
def extracttags(req: https_fn.Request) -> https_fn.Response:
    print("Executing dummy extracttags function.")
    headers = {"Access-Control-Allow-Origin": "*"}
    dummy_tags = ["test", "tag", "success"]
    return https_fn.Response(json.dumps(dummy_tags), status=200, headers=headers, content_type="application/json")

@https_fn.on_request(memory=options.MemoryOption.GB_2)
def tagplacewithreviews(req: https_fn.Request) -> https_fn.Response:
    print("Executing dummy tagplacewithreviews function.")
    headers = {"Access-Control-Allow-Origin": "*"}
    dummy_data = {"tags": ["test", "review", "success"], "intensity": "medium"}
    return https_fn.Response(json.dumps(dummy_data), status=200, headers=headers, content_type="application/json")"""
