import os
from dotenv import load_dotenv
import shutil
import json
from user_auth.utils import login_required_user 
load_dotenv()
from flask import Flask, request, jsonify, session, current_app
from flask import send_from_directory
from shared_globals import allowed_file, reverse_geocode, extract_simplified_region, extract_state_city_from_google
from werkzeug.utils import secure_filename
from collections import Counter
from utils.exif_utils import extract_gps
from geopy.distance import geodesic
import uuid
import datetime
import firebase_admin
from firebase_admin import credentials, firestore, auth
from utils.tags_extractor import extract_tags
from utils.moderation import is_description_safe 
import logging 
from utils.storage_utils import upload_to_gcs
import tempfile # Needed for temporary file handling


"""cred = credentials.Certificate("/Users/abhinavgurkar/Lokpath_list_a_place/credentials/lokpath-2d9a0-firebase-adminsdk-fbsvc-11808bd26d.json")
firebase_admin.initialize_app(cred)
db = firestore.client()"""

FIREBASE_SERVICE_ACCOUNT_CONTENT = os.environ.get('FIREBASE_SERVICE_ACCOUNT_CONTENT')

FIREBASE_SERVICE_ACCOUNT_PATH = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _initialize_firebase():
    if not firebase_admin._apps: # Check if Firebase app is not already initialized
        bucket_name = 'lokpath-2d9a0.firebasestorage.app'
        if FIREBASE_SERVICE_ACCOUNT_CONTENT:
            import json
            cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_CONTENT))
            firebase_admin.initialize_app(cred, {
                'storageBucket': bucket_name
            })
            logging.info("Firebase initialized using environment variable.")
        elif os.path.exists(FIREBASE_SERVICE_ACCOUNT_PATH):
            cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
            firebase_admin.initialize_app(cred, {
                'storageBucket': bucket_name
            })
            logging.info("Firebase initialized using local file path.")
        else:
            logging.error( # MODIFIED: Use standard logging
                f"Firebase service account not found. Expected env var FIREBASE_SERVICE_ACCOUNT_CONTENT "
                f"or file at {FIREBASE_SERVICE_ACCOUNT_PATH}. "
                f"For Google Cloud deployments, ensure service account is linked and roles are granted."
            )
            raise FileNotFoundError(
                f"Firebase service account not found. Expected env var FIREBASE_SERVICE_ACCOUNT_CONTENT "
                f"or file at {FIREBASE_SERVICE_ACCOUNT_PATH}."
            )


_initialize_firebase() # Call the helper to initialize Firebase
db = firestore.client(app=firebase_admin.get_app()) 

from user_auth.routes import create_user_bp
from guide_booking.routes import create_guide_booking_bp 
from artisan_listing.routes import create_artisan_bp
from itinerary_generator.routes import create_itinerary_bp 
from discovery_apis.routes import create_discovery_bp 
from diary.routes.diary_routes import create_diary_bp
from diary.routes.proximity_routes import create_proximity_bp
from diary.routes.progress_routes import create_progress_bp
from diary.routes.community_post_routes import create_community_post_bp

# UPLOAD_FOLDER = 'uploads'
# ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app = Flask(__name__)
# app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_fallback_secret_key_for_dev_only')
os.makedirs('uploads', exist_ok=True)

# Temporary in-memory storage

# Register blueprints
user_bp = create_user_bp(db) 
app.register_blueprint(user_bp)

guide_booking_bp = create_guide_booking_bp(db)
app.register_blueprint(guide_booking_bp)

artisan_bp = create_artisan_bp(db)
app.register_blueprint(artisan_bp)

itinerary_bp = create_itinerary_bp(db) 
app.register_blueprint(itinerary_bp)

discovery_bp = create_discovery_bp(db) 
app.register_blueprint(discovery_bp)

diary_bp = create_diary_bp(db)
app.register_blueprint(diary_bp)

proximity_bp = create_proximity_bp(db)
app.register_blueprint(proximity_bp)

progress_bp = create_progress_bp(db)
app.register_blueprint(progress_bp)

community_post_bp = create_community_post_bp(db)
app.register_blueprint(community_post_bp)



"""def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def reverse_geocode(lat, lon):
    geolocator = Nominatim(user_agent="lokpath_app")
    location = geolocator.reverse((lat, lon), exactly_one=True)
    if location:
        return location.address
    return "Unknown location" """

@app.route('/')
def home():
    return 'Server is working!'

@app.route('/manual-location', methods=['POST'])
def save_manual_location():
    data = request.get_json()
    session_id = data.get('session_id')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if not session_id or not latitude or not longitude:
        return jsonify({"error": "Missing session_id or coordinates"}), 400

    session_ref = db.collection('submission_sessions').document(session_id)
    session_ref.update({
        "gps_fallback": True,
        "manual_location": {"latitude": latitude, "longitude": longitude}
    })

    return jsonify({"message": "Manual location saved", "session_id": session_id}), 200

@app.route('/session/<session_id>', methods=['GET'])
def get_session_data(session_id):
    session_ref = db.collection('submission_sessions').document(session_id)
    doc = session_ref.get()
    if doc.exists:
        return jsonify(doc.to_dict()), 200
    else:
        return jsonify({"error": "Session not found"}), 404

@app.route('/submit-details', methods=['POST'])
def submit_details():
    data = request.get_json()
    session_id = data.get('session_id')
    description = data.get('description')
    context = data.get('context')
    budget = data.get('budget')
    kid_friendly = data.get('kid_friendly')
    pet_friendly = data.get('pet_friendly')
    wheelchair_accessible = data.get('wheelchair_accessible')
    best_time = data.get('best_time')

    if not session_id or not description or not context or not budget:
        return jsonify({"error": "Missing session_id, description, context or budget"}), 400

    session_ref = db.collection('submission_sessions').document(session_id)
    if not session_ref.get().exists:
        return jsonify({"error": "Session ID not found"}), 404
    
    is_safe, reason = is_description_safe(description)
    if not is_safe:
        return jsonify({
            "error": f"Description rejected due to inappropriate content: {reason}",
            "action": "Please revise your description."
        }), 400

    tags = extract_tags(description)

    update_data = {
        "description": data.get('description'),
        "tags": tags,
        "context": data.get('context'),
        "budget": data.get('budget'),
        "kid_friendly": data.get('kid_friendly'),
        "pet_friendly": data.get('pet_friendly'),
        "wheelchair_accessible": data.get('wheelchair_accessible'),
        "best_time": data.get('best_time'),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    session_ref.update(update_data)

    """session_store[session_id]['description'] = description
    session_store[session_id]['context'] = context
    session_store[session_id]['budget'] = budget
    session_store[session_id]['tags'] = tags
    session_store[session_id]['kid_friendly'] = kid_friendly
    session_store[session_id]['pet_friendly'] = pet_friendly
    session_store[session_id]['wheelchair_accessible'] = wheelchair_accessible
    session_store[session_id]['best_time'] = best_time"""

    return jsonify({
        "message": "Details submitted successfully",
        "session_id": session_id,
        "tags": tags
    }), 200

    """return jsonify({
        "message": "Details submitted successfully",
        "session_id": session_id,
        "description": description,
        "context": context,
        "tags": tags,
        "budget": budget
    }), 200"""

@app.route('/upload', methods=['POST'])
def upload_images():
    images = request.files.getlist('images')
    upload_type = request.args.get('type', 'gems')

    if upload_type not in ['gems', 'artisans']: # Add other types here if you expand
        return jsonify({"error": "Invalid upload type specified."}), 400

    TARGET_FOLDER = os.path.join('uploads', upload_type)
    os.makedirs(TARGET_FOLDER, exist_ok=True)

    if len(images) < 3:
        return jsonify({"error": "Please upload at least 3 images"}), 400

    gps_list = []
    session_id = str(uuid.uuid4())
    image_urls_list = []

    for file in images:
        if file and allowed_file(file.filename):
            # 1. Save to a temporary file to extract GPS
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            file.save(temp_file.name)
            gps = extract_gps(temp_file.name)
            if gps:
                gps_list.append(gps)
            
            # 2. Rewind the file and upload to GCS using your helper
            file.seek(0)
            try:
                # This now uploads to the cloud instead of saving locally
                public_url = upload_to_gcs(file, upload_type)
                image_urls_list.append(public_url)
            except Exception as e:
                current_app.logger.error(f"Failed to upload {file.filename} to GCS: {e}")
                return jsonify({"error": "Failed to upload one or more images."}), 500
            finally:
                # 3. Clean up and delete the temporary file
                temp_file.close()
                os.remove(temp_file.name)
        else:
            return jsonify({"error": f"Invalid file: {file.filename}"}), 400
    
    session_data = {
        "image_urls": image_urls_list,
        "upload_type": upload_type,
        "created_at": firestore.SERVER_TIMESTAMP,
        "gps_found_in_images": len(gps_list),
    }

    if not gps_list:
        session_data.update({
            "gps_fallback": True,
            "reason": "no_gps_found",
        })
        db.collection('submission_sessions').document(session_id).set(session_data)
        current_app.logger.info(f"Session {session_id}: Images uploaded to {upload_type}, no GPS found. Prompting manual location.")
        return jsonify({
            "message": "Images uploaded but no GPS found",
            "action": "Prompt user to drop pin manually",
            "session_id": session_id
        }), 200
    
    too_far = False
    for i in range(len(gps_list)):
        for j in range(i+1, len(gps_list)):
            dist = geodesic(
                (gps_list[i]['latitude'], gps_list[i]['longitude']),
                (gps_list[j]['latitude'], gps_list[j]['longitude'])
            ).km
            if dist > 1:  # Customize distance threshold here
                too_far = True
                break

    if too_far:
        session_data.update({
            "gps_fallback": True,
            "reason": "gps_variation",
            "gps_points": gps_list,
        })
        # MODIFIED: Write to Firestore before returning
        db.collection('submission_sessions').document(session_id).set(session_data)
        return jsonify({
            "message": "Images are from very different locations",
            "action": "Prompt user to choose location manually",
            "session_id": session_id
        }), 200

    # Use most common GPS coordinates
    latitudes = [round(g['latitude'], 4) for g in gps_list]
    longitudes = [round(g['longitude'], 4) for g in gps_list]

    most_common_lat = Counter(latitudes).most_common(1)[0][0]
    most_common_lon = Counter(longitudes).most_common(1)[0][0]

    google_address_components = reverse_geocode(most_common_lat, most_common_lon)
    if not google_address_components:
        # Fallback to Nominatim if Google fails
        nominatim_address = reverse_geocode_nominatim_fallback(most_common_lat, most_common_lon)
        session_data.update({
            "gps_fallback": False,
            "suggested_location": {
                "latitude": most_common_lat,
                "longitude": most_common_lon,
                "region_name": nominatim_address # Store the full address for display
            },
            "gps_found_in_images": len(gps_list),
        })
        db.collection('submission_sessions').document(session_id).set(session_data)
        return jsonify({
            "message": "Images uploaded successfully (using Nominatim fallback)",
            "session_id": session_id,
            "suggested_location": { "latitude": most_common_lat, "longitude": most_common_lon, "region_name": nominatim_address },
            "gps_found_in_images": len(gps_list)
        }), 200

    state, city = extract_state_city_from_google(google_address_components)

    session_data.update({
        "gps_fallback": False,
        "suggested_location": {
            "latitude": most_common_lat,
            "longitude": most_common_lon,
            "full_address": google_address_components['full_address'],
            "state": state,
            "city": city
        },
    })

    db.collection('submission_sessions').document(session_id).set(session_data)

    current_app.logger.info(f"Session {session_id}: Images uploaded to {upload_type}, GPS extracted. Suggested location: {city}, {state}")
    return jsonify({
        "message": "Images uploaded successfully",
        "session_id": session_id,
        "suggested_location": {
            "latitude": most_common_lat,
            "longitude": most_common_lon,
            "full_address": google_address_components['full_address'],
            "state": state,
            "city": city
        },
        "gps_found_in_images": len(gps_list)
    }), 200


@app.route('/finalize/<session_id>', methods=['GET'])
def finalize_json(session_id):
    session_ref = db.collection('submission_sessions').document(session_id)
    doc = session_ref.get()
    if not doc.exists:
        return jsonify({"error": "Session not found"}), 404
    data = doc.to_dict()

    coords = data.get("suggested_location") or data.get("manual_location") or {}
    preview_image_urls = data.get("image_urls", [])
    

    return jsonify({
        "description": data.get("description"),
        "tags": data.get("tags", []),
        "budget_category": data.get("budget"),
        "context": data.get("context", {}),
        "kid_friendly": data.get("kid_friendly"),
        "pet_friendly": data.get("pet_friendly"),
        "wheelchair_accessible": data.get("wheelchair_accessible"),
        "best_time": data.get("best_time"),
        "coordinates": {
            "lat": coords.get("latitude"),
            "lng": coords.get("longitude")
        },
        "region_name": coords.get("full_address") or coords.get("region_name"),
        "session_id": session_id,
        "source": "image_extracted" if not data.get("gps_fallback") else "manual",
        "added_by": data["context"]["relationship"] if "context" in data else "visitor",
        "timestamp": data.get("timestamp"),
        "image_urls": preview_image_urls
    }), 200

@app.route('/upload-to-firebase/<session_id>', methods=['POST'])
@login_required_user 
def upload_to_firebase(session_id):
    session_ref = db.collection('submission_sessions').document(session_id)
    doc = session_ref.get()
    if not doc.exists:
        return jsonify({"error": "Session not found"}), 404
    data = doc.to_dict()

    description = data.get("description")
    tags = data.get("tags", [])
    budget = data.get("budget")
    context = data.get("context", {})
    image_paths_for_firestore = data.get("image_urls", [])
    user_uid = session.get('user_uid')
    added_by_uid_field = user_uid if user_uid else "anonymous" 

    final_data = {
        "description": description,
        "tags": tags,
        "budget_category": budget,
        "context": context,
        "coordinates": {},
        "session_id": session_id,
        "added_by_uid": added_by_uid_field,
        "source": "manual" if data.get("gps_fallback") else "image_extracted",
        "added_by_relationship": context.get("relationship"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "image_urls": image_paths_for_firestore,
        "kid_friendly": data.get("kid_friendly"),
        "pet_friendly": data.get("pet_friendly"),
        "wheelchair_accessible": data.get("wheelchair_accessible"),
        "best_time": data.get("best_time"),
        "status": "pending_review",
    }

    coords = data.get("suggested_location") or data.get("manual_location") or {}
    if not data.get("gps_fallback"):
        if coords and 'latitude' in coords and 'longitude' in coords:
            final_data["coordinates"] = {"lat": coords["latitude"], "lng": coords["longitude"]}
            # Use the new state and city from Google's response
            state_name_for_firestore = coords.get("state")
            city_name_for_firestore = coords.get("city")
            final_data["region_name"] = coords.get("full_address") # Store full address
            final_data["state_name"] = state_name_for_firestore
            final_data["city_name"] = city_name_for_firestore
        else:
             current_app.logger.warning(f"Session {session_id}: gps_fallback is False but suggested_location is missing or incomplete.")
             state_name_for_firestore, city_name_for_firestore = "Unknown_State", "Unknown_City"
             final_data["region_name"] = "Unknown Location"
    else:
        if coords and 'latitude' in coords and 'longitude' in coords:
            final_data["coordinates"] = {"lat": coords["latitude"], "lng": coords["longitude"]}
            state_name_for_firestore, city_name_for_firestore = "Manual_Submissions_State", "Manual_Submissions_City"
            final_data["region_name"] = "Manual Submissions"
        else:
            current_app.logger.warning(f"Session {session_id}: gps_fallback is True but manual_location is missing or incomplete.")
            state_name_for_firestore, city_name_for_firestore = "Unknown_State", "Unknown_City"
            final_data["region_name"] = "Unknown Location"


    
    push_to_firestore(state_name_for_firestore, city_name_for_firestore, session_id, final_data)

    try:
        if session.get('user_uid'):
            user_profile_ref = db.collection('users').document(user_uid)
            user_doc = user_profile_ref.get() # <--- CHECK IF USER DOC EXISTS
            
            # --- NEW LOGIC START ---
            if not user_doc.exists:
                # If it doesn't exist, create it with initial data.
                # This prevents the 'No document to update' error.
                user_profile_ref.set({
                    'submitted_gems_count': 0,
                    'artisans_listed_count': 0,
                    'cancellation_count': 0,
                    'last_active': firestore.SERVER_TIMESTAMP
                })
            # --- NEW LOGIC END ---

            # Store a copy of the gem data in a subcollection under the user
            user_gems_ref = db.collection('users').document(user_uid).collection('hidden_gems_listed').document(session_id)
            user_gems_ref.set(final_data)

            # Now it's safe to update the submitted_gems_count
            user_profile_ref.update({'submitted_gems_count': firestore.Increment(1)})
            current_app.logger.info(f"Incremented submitted_gems_count for user {user_uid}.")

        # Clean up session store after successful finalization
        session_ref.delete()
        current_app.logger.info(f"Session {session_id} data finalized and removed from session_store.")

        return jsonify({"message": "Data uploaded to Firebase successfully!", "gem_id": session_id}), 201 
    except Exception as e:
        current_app.logger.error(f"Error finalizing hidden gem submission {session_id}: {e}")
        return jsonify({"error": "Failed to finalize hidden gem submission.", "details": str(e)}), 500

def push_to_firestore(state_name, city_name, session_id, data):
    # New hierarchical path
    state_doc_ref = db.collection('hidden_gems').document(state_name)
    city_doc_ref = state_doc_ref.collection('cities').document(city_name)
    gem_submission_doc_ref = city_doc_ref.collection('gem_submissions').document(session_id)

    gem_submission_doc_ref.set(data)
    current_app.logger.info(f"Hidden gem {session_id} added to Firestore under State: {state_name}, City: {city_name}.")


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # Note: Ensure your main app has an 'uploads' folder
    return send_from_directory("uploads", filename)

@app.route("/user-itinerary/<user_id>/diary-feed", methods=["GET"])
def diary_feed(user_id):
    root_path = os.path.join("uploads", "diary_photos", user_id)
    if not os.path.exists(root_path):
        return jsonify({"message": "No trips found", "photos": []})

    all_photos = []

    for trip_id in os.listdir(root_path):
        trip_folder = os.path.join(root_path, trip_id)
        meta_file = os.path.join(trip_folder, "photo_metadata.json")

        if os.path.exists(meta_file):
            with open(meta_file, "r") as f:
                try:
                    trip_photos = json.load(f)
                    for p in trip_photos:
                        p["trip_id"] = trip_id
                        all_photos.append(p)
                except Exception as e:
                    print(f"Error loading metadata for {trip_id}: {e}")

    all_photos.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return jsonify({
        "user_id": user_id,
        "photo_count": len(all_photos),
        "photos": all_photos
    })


if __name__ == '__main__':
    app.run(debug=True)
