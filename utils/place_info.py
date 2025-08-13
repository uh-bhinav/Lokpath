# utils.py

import os 

def load_google_api_key():
    """
    Loads the Google API key from credentials/google_api_key.txt.
    """
    # ✅ Look in parent directory for credentials
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(parent_dir, "credentials", "google_api_key")
    
    if not os.path.exists(path):
        raise FileNotFoundError(f"Google API key file not found at {path}")
    
    with open(path, "r") as file:
        return file.read().strip()
# utils.py

def map_price_level(level):
    """
    Maps Google's numeric price_level (0-4) to a human-friendly budget category.
    Adds built-in safety for invalid inputs and unknown cases.
    """
    # Handle missing or invalid levels
    if level is None:
        return {"category": "unknown", "disclaimer": "⚠️ No price info available"}
    if not isinstance(level, (int, float)):
        return {"category": "unknown", "disclaimer": "⚠️ Invalid price data"}

    # Map numeric levels to categories
    if level <= 1:
        return {"category": "low", "disclaimer": ""}
    elif level == 2:
        return {"category": "mid", "disclaimer": ""}
    elif level >= 3:
        return {"category": "high", "disclaimer": ""}

    # Fallback for edge cases
    return {"category": "unknown", "disclaimer": "⚠️ No price info available"}
