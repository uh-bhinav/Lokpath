# shared_globals.py
import os
import googlemaps
from collections import Counter
from geopy.distance import geodesic # Keep this for distance calculations
from werkzeug.utils import secure_filename 

# --- Global Variables ---
session_store = {}

# --- Geocoding API Client (read key from env) ---
Maps_API_KEY = os.environ.get('Maps_API_KEY')
gmaps_client = googlemaps.Client(key=Maps_API_KEY)

# --- Helper Functions ---
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    """Checks if a file's extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def reverse_geocode(lat, lon):
    """
    Performs reverse geocoding using Google Maps API.
    Returns a structured dictionary of address components.
    """
    try:
        # Google Maps Geocoding API is highly structured and reliable
        geocode_result = gmaps_client.reverse_geocode((lat, lon))
        if geocode_result:
            address_components = {}
            # Extract key components from the first result
            for component in geocode_result[0]['address_components']:
                # Use the short name if available, otherwise long name
                component_type = component['types'][0]
                address_components[component_type] = component['short_name'] if 'short_name' in component else component['long_name']

            # Also return the full formatted address
            address_components['full_address'] = geocode_result[0]['formatted_address']

            return address_components

    except Exception as e:
        # We are not in a Flask app context here, so print to console
        print(f"Error during Google Maps reverse geocoding for {lat},{lon}: {e}")

    return None # Return None on failure

def extract_simplified_region(full_address):
    """Extracts a simplified region name from a full address string (for Nominatim fallback if needed)."""
    # This function is now mainly a fallback or used for consistency, as Google provides structured data.
    if full_address:
        address_parts = [part.strip().replace(' District', '') for part in full_address.split(',')]
        if address_parts and len(address_parts[0]) > 1:
            return address_parts[0].title()
        for part in address_parts:
            if part and part.lower() not in ["india", "state", "province", "city", "county", "republic"] and len(part) > 1:
                return part.title()
        return "Unknown Region"
    return "Unknown Region"

def extract_state_city_from_google(address_components):
    """
    Extracts state and city from a structured Google Maps API response.
    This is far more reliable than parsing a string.
    """
    state = address_components.get('administrative_area_level_1', 'Unknown State')
    city = address_components.get('locality') or \
           address_components.get('administrative_area_level_2') or \
           'Unknown City'
    return state, city