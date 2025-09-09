# Itinerarybuilder/utils/place_info.py
import os

def load_google_api_key():
    """
    Loads the Google API key from the 'Maps_API_KEY' environment variable.
    """
    api_key = os.environ.get('Maps_API_KEY')
    if not api_key:
        raise ValueError("Google Maps API key not found. Ensure 'Maps_API_KEY' is set in your .env file.")
    return api_key

def map_price_level(level):
    """
    Maps Google's price_level (0–4) to human-friendly categories.
    """
    if level is None or level == -1:
        return "unknown"
    
    try:
        level = int(level)
    except (ValueError, TypeError):
        return "unknown"

    if level <= 1:
        return "low"
    elif level == 2:
        return "mid"
    elif level >= 3:
        return "high"
    else:
        return "unknown"