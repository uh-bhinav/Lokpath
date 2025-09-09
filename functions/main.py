# functions/main.py

import os
import datetime
import tempfile
from firebase_functions import firestore_fn, storage_fn, scheduler_fn
from firebase_admin import initialize_app, storage, firestore
from PIL import Image
import pillow_heif

# Initialize Firebase Admin SDK
# This is done once when the function instance starts up.
initialize_app()
pillow_heif.register_heif_opener()

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

@firestore_fn.on_document_written("guides/{guideId}/reviews/{reviewId}")
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


@firestore_fn.on_document_created("bookings/{bookingId}")
def assign_guide_to_booking(event: firestore_fn.Event[firestore_fn.Change]) -> None:
    """
    Triggered when a new booking document is created.
    Assigns the first guide in the potential_guides list to the booking.
    """
    booking_ref = event.reference
    booking_data = event.data.to_dict()

    # Only act on bookings that are newly created and need assignment
    if booking_data.get("status") != "pending_assignment":
        print(f"Booking {booking_ref.id} is not pending assignment. Skipping.")
        return

    potential_guides = booking_data.get("potential_guides", [])
    if not potential_guides:
        print(f"Booking {booking_ref.id} has no potential guides. Marking as failed.")
        booking_ref.update({"status": "failed", "failure_reason": "No guides found"})
        return

    # Assign the first guide from the list
    assigned_guide_uid = potential_guides[0]
    
    # Set the response deadline to 60 minutes from now
    assignment_time = datetime.datetime.now(datetime.timezone.utc)
    deadline = assignment_time + datetime.timedelta(minutes=60)

    # Update the booking document
    booking_ref.update({
        "status": "pending_acceptance",
        "assigned_guide_uid": assigned_guide_uid,
        "guide_response_deadline": deadline.isoformat(),
        "assignment_history": firestore.ArrayUnion([{
            "guide_uid": assigned_guide_uid,
            "assigned_at": assignment_time.isoformat(),
            "status": "pending"
        }])
    })

    print(f"Assigned guide {assigned_guide_uid} to booking {booking_ref.id}. Deadline: {deadline.isoformat()}")

    # --- TODO: Send a real push notification to the guide ---
    # For now, this is simulated with a log message.
    print(f"NOTIFICATION: Sent to guide {assigned_guide_uid} about new booking {booking_ref.id}.")

@firestore_fn.on_document_updated("bookings/{bookingId}")
def handle_booking_rejection(event: firestore_fn.Event[firestore_fn.Change]) -> None:
    """
    Triggered when a booking is updated. If a guide rejected the booking,
    this function assigns the next guide in the list.
    """
    before_data = event.data.before.to_dict()
    after_data = event.data.after.to_dict()
    booking_ref = event.reference

    # We only care about the transition to "rejected_by_guide"
    if not (before_data.get("status") == "pending_acceptance" and after_data.get("status") == "rejected_by_guide"):
        return

    print(f"Handling rejection for booking {booking_ref.id} by guide {before_data.get('assigned_guide_uid')}")

    potential_guides = after_data.get("potential_guides", [])
    rejected_guide_uid = before_data.get("assigned_guide_uid")

    try:
        # Find the index of the guide who just rejected the offer
        rejected_index = potential_guides.index(rejected_guide_uid)
    except ValueError:
        print(f"Error: Rejected guide {rejected_guide_uid} not found in potential_guides list for booking {booking_ref.id}.")
        booking_ref.update({"status": "failed", "failure_reason": "Internal error: guide list mismatch."})
        return

    # Try to find the next guide in the list
    next_guide_index = rejected_index + 1
    if next_guide_index < len(potential_guides):
        # There is another guide to try
        next_guide_uid = potential_guides[next_guide_index]
        assignment_time = datetime.datetime.now(datetime.timezone.utc)
        deadline = assignment_time + datetime.timedelta(minutes=60)

        booking_ref.update({
            "status": "pending_acceptance",
            "assigned_guide_uid": next_guide_uid,
            "guide_response_deadline": deadline.isoformat(),
            "assignment_history": firestore.ArrayUnion([{
                "guide_uid": next_guide_uid,
                "assigned_at": assignment_time.isoformat(),
                "status": "pending"
            }])
        })
        print(f"Re-assigned booking {booking_ref.id} to next guide {next_guide_uid}.")
        print(f"NOTIFICATION: Sent to guide {next_guide_uid} about new booking {booking_ref.id}.")
    else:
        # No more guides left to assign
        print(f"No more guides to assign for booking {booking_ref.id}. Marking as failed.")
        booking_ref.update({"status": "failed", "failure_reason": "All available guides rejected the request."})
        # TODO: Notify the tourist that no guide could be found
        tourist_uid = after_data.get("tourist_uid")
        print(f"NOTIFICATION: Sent to tourist {tourist_uid} that no guide could be found for booking {booking_ref.id}.")


@scheduler_fn.on_schedule(schedule="every 5 minutes")
def check_booking_status(event: scheduler_fn.ScheduledEvent) -> None:
    """
    Runs every 5 minutes to check for pending bookings that have timed out
    or need a reminder notification.
    """
    db = firestore.client()
    now = datetime.datetime.now(datetime.timezone.utc)

    # Query for all bookings that are currently waiting for a guide's response
    query = db.collection("bookings").where("status", "==", "pending_acceptance")
    pending_bookings = query.stream()

    for doc in pending_bookings:
        booking_data = doc.to_dict()
        deadline_str = booking_data.get("guide_response_deadline")
        if not deadline_str: continue

        deadline = datetime.datetime.fromisoformat(deadline_str)
        minutes_left = (deadline - now).total_seconds() / 60

        # 1. Handle Timeouts
        if minutes_left <= 0:
            print(f"Booking {doc.id} has timed out. Updating status.")
            doc.reference.update({"status": "timed_out"})
            continue # The on_document_updated function will handle re-assignment

        # 2. Handle Reminders
        reminders = booking_data.get("reminders_sent", {})
        
        # 30-minute reminder (window is 25-30 mins left)
        if 25 < minutes_left <= 30 and not reminders.get("thirty_minute"):
            doc.reference.update({"reminders_sent.thirty_minute": True})
            print(f"NOTIFICATION: Sending 30-minute reminder to guide for booking {doc.id}.")

        # 5-minute reminder (window is 1-5 mins left)
        elif 1 < minutes_left <= 5 and not reminders.get("five_minute"):
            doc.reference.update({"reminders_sent.five_minute": True})
            print(f"NOTIFICATION: Sending 5-minute final reminder to guide for booking {doc.id}.")
