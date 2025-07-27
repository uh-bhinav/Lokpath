import os
from dotenv import load_dotenv
import shutil
from user_auth.utils import login_required_user
load_dotenv()
from flask import Flask, request, jsonify, session, current_app
from shared_globals import session_store, allowed_file, reverse_geocode
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

from query_firestore import get_filtered_pois
from fetch_places import fetch_places
from get_reviews import get_reviews_for_place
from tag_reviews import tag_place_with_reviews, has_kid_friendly_issues
from itinerary_builder import generate_itinerary
from store_pois import store_pois
from store_firestore import store_itinerary
from utils.itinerary_utils import estimate_required_pois, infer_kid_friendly
from utils.place_info import map_price_level


"""cred = credentials.Certificate("/Users/abhinavgurkar/Lokpath_list_a_place/credentials/lokpath-2d9a0-firebase-adminsdk-fbsvc-11808bd26d.json")
firebase_admin.initialize_app(cred)
db = firestore.client()"""


# Load Firebase service account path from environment
FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
def _initialize_firebase():
    if not FIREBASE_SERVICE_ACCOUNT_PATH:
        raise EnvironmentError(
            "FIREBASE_SERVICE_ACCOUNT_PATH environment variable not set"
        )
    if not firebase_admin._apps:  # Check if Firebase app is not already initialized
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)

_initialize_firebase() # Call the helper to initialize Firebase
db = firestore.client(app=firebase_admin.get_app()) 

from user_auth.routes import create_user_bp
from guide_booking.routes import create_guide_booking_bp 
from artisan_listing.routes import create_artisan_bp

# UPLOAD_FOLDER = 'uploads'
# ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app = Flask(__name__)
# app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_fallback_secret_key_for_dev_only')
os.makedirs('uploads', exist_ok=True)

# Temporary in-memory storage

# session_store = {}

user_bp = create_user_bp(db) 
app.register_blueprint(user_bp)

guide_booking_bp = create_guide_booking_bp(db)
app.register_blueprint(guide_booking_bp)

artisan_bp = create_artisan_bp(db)
app.register_blueprint(artisan_bp)

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

    session_store[session_id] = {
        "gps_fallback": True,
        "manual_location": {"latitude": latitude, "longitude": longitude}
    }

    return jsonify({"message": "Manual location saved", "session_id": session_id}), 200

@app.route('/session/<session_id>', methods=['GET'])
def get_session_data(session_id):
    data = session_store.get(session_id)
    if data:
        return jsonify(data), 200
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

    if session_id not in session_store:
        return jsonify({"error": "Session ID not found"}), 404
    
    is_safe, reason = is_description_safe(description)
    if not is_safe:
        return jsonify({
            "error": f"Description rejected due to inappropriate content: {reason}",
            "action": "Please revise your description."
        }), 400

    tags = extract_tags(description)

    session_store[session_id].update({
        "description": description,
        "tags": tags,
        "context": context,
        "budget": budget,
        "kid_friendly": kid_friendly,
        "pet_friendly": pet_friendly,
        "wheelchair_accessible": wheelchair_accessible,
        "best_time": best_time,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })

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
    session_store[session_id] = {"image_filenames": [], "upload_type": upload_type}

    for file in images:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(TARGET_FOLDER, filename)
            file.save(filepath)
            session_store[session_id]["image_filenames"].append(os.path.join(upload_type, filename))

            gps = extract_gps(filepath)
            if gps:
                gps_list.append(gps)
        else:
            return jsonify({"error": f"Invalid file: {file.filename}"}), 400

    if not gps_list:
        session_store[session_id].update({
            "gps_fallback": True,
            "reason": "no_gps_found",
        })
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
        session_store[session_id].update({
            "gps_fallback": True,
            "reason": "gps_variation",
            "gps_points": gps_list,
        })
        current_app.logger.info(f"Session {session_id}: GPS coordinates vary significantly. Prompting manual location.")
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

    region_name = reverse_geocode(most_common_lat, most_common_lon)

    session_store[session_id].update({
        "gps_fallback": False,
        "suggested_location": {
            "latitude": most_common_lat,
            "longitude": most_common_lon,
            "region_name": region_name
        },
        "gps_found_in_images": len(gps_list),
    })
    current_app.logger.info(f"Session {session_id}: Images uploaded to {upload_type}, GPS extracted. Suggested location: {region_name}")
    return jsonify({
        "message": "Images uploaded successfully",
        "session_id": session_id,
        "suggested_location": {
            "latitude": most_common_lat,
            "longitude": most_common_lon,
            "region_name": region_name
        },
        "gps_found_in_images": len(gps_list)
    }), 200

@app.route('/finalize/<session_id>', methods=['GET'])
def finalize_json(session_id):
    data = session_store.get(session_id)
    if not data:
        return jsonify({"error": "Session not found"}), 404

    coords = data.get("suggested_location") or data.get("manual_location") or {}
    image_filenames = data.get("image_filenames", [])
    preview_image_urls = [f"/uploads/{f}" for f in image_filenames]

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
        "region_name": coords.get("region_name"),
        "session_id": session_id,
        "source": "image_extracted" if not data.get("gps_fallback") else "manual",
        "added_by": data["context"]["relationship"] if "context" in data else "visitor",
        "timestamp": data.get("timestamp"),
        "image_urls": preview_image_urls
    }), 200

@app.route('/upload-to-firebase/<session_id>', methods=['POST'])
@login_required_user 
def upload_to_firebase(session_id):
    data = session_store.get(session_id)
    if not data:
        return jsonify({"error": "Session not found"}), 404

    description = data.get("description")
    tags = data.get("tags", [])
    budget = data.get("budget")
    context = data.get("context", {})
    image_paths_for_firestore = []
    for filename in data.get("image_filenames", []): 
        image_paths_for_firestore.append(f"/uploads/{filename}")

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

    if not data.get("gps_fallback"):
        loc = data.get("suggested_location")
        final_data["coordinates"] = {
            "lat": loc["latitude"],
            "lng": loc["longitude"]
        }
        region = loc["region_name"].split(",")[0].strip()
    else:
        loc = data.get("manual_location")
        final_data["coordinates"] = {
            "lat": loc["latitude"],
            "lng": loc["longitude"]
        }
        region = "Unknown"

    push_to_firestore(region, session_id, final_data)

    try:
        if user_uid:
            user_doc_ref = db.collection('users').document(user_uid)
            # Atomically increment the submitted_gems_count
            user_doc_ref.update({'submitted_gems_count': firestore.Increment(1)})
            current_app.logger.info(f"Incremented submitted_gems_count for user {user_uid}.")

        # Clean up session store after successful finalization
        del session_store[session_id]
        current_app.logger.info(f"Session {session_id} data finalized and removed from session_store.")

        return jsonify({"message": "Data uploaded to Firebase successfully!", "gem_id": session_id}), 201 
    except Exception as e:
        current_app.logger.error(f"Error finalizing hidden gem submission {session_id}: {e}")
        return jsonify({"error": "Failed to finalize hidden gem submission.", "details": str(e)}), 500

def push_to_firestore(region_name, session_id, data):
    region_doc = db.collection('hidden_gems').document(region_name)
    session_doc = region_doc.collection('gem_submissions').document(session_id)
    session_doc.set(data)


@app.route('/itinerary/generate', methods=['POST'])
def generate_itinerary_route():
    """Generate an itinerary based on user trip parameters."""
    user_input = request.get_json() or {}

    required_fields = ["user_id", "location", "start_date", "end_date"]
    missing = [f for f in required_fields if f not in user_input]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        required_pois = estimate_required_pois(
            user_input["start_date"], user_input["end_date"]
        )

        filtered_pois = get_filtered_pois(user_input)

        if len(filtered_pois) < required_pois:
            new_places = fetch_places(user_input["location"])
            for place in new_places:
                reviews = get_reviews_for_place(place["place_id"])
                tags = tag_place_with_reviews(place["name"], reviews)
                kid_warning = has_kid_friendly_issues(reviews)
                place["tags"] = tags
                place["budget_category"] = map_price_level(place.get("price_level"))
                if kid_warning:
                    place["kid_friendly"] = False
                else:
                    place["kid_friendly"] = True if infer_kid_friendly(tags) is True else None
                place.setdefault("pet_friendly", False)
                place.setdefault("wheelchair_accessible", False)
                place.setdefault("disclaimer", "")

            store_pois(user_input["location"], new_places)
            filtered_pois = get_filtered_pois(user_input)

        itinerary = generate_itinerary(
            filtered_pois,
            user_input["start_date"],
            user_input["end_date"],
            enable_hidden_gems=True,
        )

        trip_id = str(uuid.uuid4())
        store_itinerary(
            user_input["user_id"],
            user_input["location"],
            user_input["start_date"],
            user_input["end_date"],
            itinerary,
            trip_id,
        )

        return jsonify({"trip_id": trip_id, "itinerary": itinerary})

    except Exception as e:
        current_app.logger.error(f"Error generating itinerary: {e}")
        return jsonify({"error": "Itinerary generation failed", "details": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
