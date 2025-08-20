# itinerary_generator/utils/google_places_utils.py

import requests
import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

BASE_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"


def fetch_places_from_google(query: str, location: str = None, radius: int = 5000, max_results: int = 10):
    """
    Fetch POIs from Google Places API based on a query and optional location.
    
    Args:
        query (str): Search query (e.g., "tourist attractions in Coorg").
        location (str, optional): Lat,long coordinates (e.g., "12.3375,75.8069").
        radius (int, optional): Search radius in meters. Default: 5000m.
        max_results (int, optional): Maximum number of POIs to return. Default: 10.

    Returns:
        list: A list of dictionaries containing cleaned POI data.
    """
    params = {
        "query": query,
        "key": GOOGLE_PLACES_API_KEY,
    }
    if location:
        params["location"] = location
        params["radius"] = radius

    results = []
    next_page_token = None

    while len(results) < max_results:
        if next_page_token:
            params["pagetoken"] = next_page_token

        response = requests.get(BASE_URL, params=params)
        data = response.json()

        if "error_message" in data:
            raise Exception(f"Google Places API Error: {data['error_message']}")

        places = data.get("results", [])
        for place in places:
            results.append(clean_place_data(place))
            if len(results) >= max_results:
                break

        # Handle pagination
        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break

    return results


def clean_place_data(place: dict) -> dict:
    """
    Extract and clean relevant fields from Google Places API response.

    Args:
        place (dict): Raw Google Place result.

    Returns:
        dict: Cleaned POI dictionary.
    """
    return {
        "name": place.get("name"),
        "address": place.get("formatted_address"),
        "location": place.get("geometry", {}).get("location", {}),
        "rating": place.get("rating", None),
        "user_ratings_total": place.get("user_ratings_total", 0),
        "place_id": place.get("place_id"),
        "types": place.get("types", []),
        "photos": extract_photo_reference(place),
    }


def extract_photo_reference(place: dict) -> list:
    """
    Extract photo references if available from Google Places API result.

    Args:
        place (dict): Raw Google Place result.

    Returns:
        list: A list of photo reference strings.
    """
    photos = place.get("photos", [])
    return [photo.get("photo_reference") for photo in photos if "photo_reference" in photo]
