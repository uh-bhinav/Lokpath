# In utils/storage_utils.py

from firebase_admin import storage
import uuid

def upload_to_gcs(file_object, destination_folder):
    """
    Uploads a file object to Firebase Cloud Storage and returns its public URL.

    :param file_object: The file object to upload (from request.files).
    :param destination_folder: The folder in the bucket (e.g., 'gems' or 'artisans').
    :return: The public URL of the uploaded file.
    """
    # Get the default bucket from your Firebase project
    bucket = storage.bucket()

    # Create a unique filename to prevent overwrites
    filename = f"{uuid.uuid4()}_{file_object.filename}"
    blob = bucket.blob(f"{destination_folder}/{filename}")

    # Upload the file from the in-memory file object
    blob.upload_from_file(
        file_object,
        content_type=file_object.content_type
    )

    # Make the file publicly accessible
    blob.make_public()

    # Return the public URL
    return blob.public_url