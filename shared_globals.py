import os
from collections import Counter
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from werkzeug.utils import secure_filename # For allowed_file

# --- Global Variables ---
session_store = {} # Temporary in-memory storage for multi-step forms

# --- Helper Functions (moved from app.py) ---
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'} # Defined here as it's used by allowed_file

def allowed_file(filename):
    """Checks if a file's extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def reverse_geocode(lat, lon):
    """Performs reverse geocoding to get a location address from lat/lon."""
    geolocator = Nominatim(user_agent="lokpath_app", timeout=5)
    try:
        location = geolocator.reverse((lat, lon), exactly_one=True)
        if location:
            return location.address
    except Exception as e:
        # current_app is not available here, so just print or log to file
        print(f"Error during reverse geocoding for {lat},{lon}: {e}")
    return "Unknown location"

def extract_simplified_region(location_address):
    
    if location_address:
        # Split by comma, strip whitespace, remove " District"
        address_parts = [part.strip().replace(' District', '') for part in location_address.split(',')]
        
        # Prioritize the first part if it's substantial (e.g., "Coorg", "Bengaluru")
        if address_parts and len(address_parts[0]) > 1: # >1 to include short city names like "Delhi"
            return address_parts[0].title()
        
        # Fallback to other parts if the first is generic or too short
        # This list of terms can be expanded
        for part in address_parts:
            if part and part.lower() not in ["india", "state", "province", "city", "county", "republic"] and len(part) > 1:
                return part.title()
        
        # Default fallback
        return "Unknown Region"
    return "Unknown Region"