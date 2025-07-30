# utils/place_info.py

import os

def load_google_api_key():
    """
    Loads the Google API key from credentials/google_api_key.txt.
    """
    path = os.path.join("credentials", "google_api_key.txt")
    if not os.path.exists(path):
        raise FileNotFoundError("Google API key file not found at credentials/google_api_key.txt")
    
    with open(path, "r") as file:
        return file.read().strip()

def map_price_level(level):
    """
    Maps Google's price_level (0–4) to human-friendly categories.
    Handles unknown values and ensures scaling safety.
    Returns just the category string (not a dict).
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