import os

def load_google_api_key():
    """
    Loads the Google API key from credentials/google_api_key.txt.
    """
    # ✅ Look in parent directory for credentials
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(parent_dir, "credentials", "google_api_key.txt")
    
    if not os.path.exists(path):
        raise FileNotFoundError(f"Google API key file not found at {path}")
    
    with open(path, "r") as file:
        return file.read().strip()

def map_price_level(level):
    """
    Maps Google's price_level (0–4) to human-friendly categories.
    Returns just the category string (not a dict) for compatibility.
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