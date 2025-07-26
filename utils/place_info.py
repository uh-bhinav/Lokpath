# utils.py

def load_google_api_key():
    with open("credentials/google_api_key.txt", "r") as file:
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
