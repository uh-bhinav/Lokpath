# 🗺️ LokPath – AI Itinerary Builder (Backend Feature)

## 📌 Overview
This module powers the **AI-based itinerary generation** for LokPath. It:
- Fetches Places of Interest (POIs) dynamically using **Google Places API**.
- Scrapes Google reviews and tags POIs using **BERT zero-shot classification**.
- Filters POIs based on **budget, accessibility, kids/pets/disabilities**.
- Generates **multi-day itineraries** with rest logic and hidden gem placeholders.
- Stores user itineraries in **Firebase Firestore** under unique trip IDs.

---

## 🛠️ Requirements

### 1️⃣ API Keys & Accounts
- **Google Cloud Project** with:
  - Google Places API
  - Place Details API
  - Geocoding API
- **Firebase Project** with:
  - Firestore Database
  - Firebase Admin SDK JSON

### 2️⃣ Python Environment
- Python 3.10 or above
- Virtual environment recommended (`venv`)

### 3️⃣ Dependencies (add to `requirements.txt`)


googlemaps
firebase-admin
requests
transformers
torch
tqdm

yaml
Copy
Edit

---

## 📂 File Structure
lokpath/
│── run_pipeline.py # Orchestrates the entire flow
│── fetch_places.py # Fetch POIs dynamically using Google Places API
│── get_reviews.py # Fetch reviews for each POI
│── tag_reviews.py # BERT-based review tagging
│── itinerary_builder.py # Generates the final itinerary
│── query_firestore.py # Filters POIs from Firestore
│── store_pois.py # Saves new POIs to Firestore
│── store_firestore.py # Saves user itineraries to Firestore
│── utils/
│ ├── place_info.py # API key loader + price level mapping
│ └── itinerary_utils.py # Estimation logic for required POIs
│── credentials/
│ ├── lokpath-admin.json # Firebase Admin SDK Key (ignored in git)
│ └── google_api_key.txt # Google API Key (ignored in git)



---

## 🚀 How to Run

### 1️⃣ Prepare `run_pipeline.py`
A sample pipeline script should look like this:

```python
from query_firestore import get_filtered_pois
from fetch_places import fetch_places
from get_reviews import get_reviews_for_place
from tag_reviews import tag_place_with_reviews
from itinerary_builder import generate_itinerary
from store_pois import store_pois
from store_firestore import store_itinerary
from utils.itinerary_utils import estimate_required_pois
from utils.place_info import map_price_level
import uuid

# 🧪 User Input
user_input = {
    "user_id": "user_123",
    "location": "Paris",
    "start_date": "2025-05-01",
    "end_date": "2025-05-07",
    "selected_interests": ["sunset", "romantic", "peaceful", "trek"],
    "budget": "low",
    "with_kids": True,
    "with_pets": False,
    "with_disabilities": False
}

# ✅ Estimate POIs
required_pois = estimate_required_pois(user_input["start_date"], user_input["end_date"])

# 🔎 Query Firestore
filtered_pois = get_filtered_pois(user_input)

# 📥 Fetch from Google if insufficient POIs
if len(filtered_pois) < required_pois:
    new_places = fetch_places(user_input["location"])
    for place in new_places:
        reviews = get_reviews_for_place(place["place_id"])
        tags = tag_place_with_reviews(place["name"], reviews)
        place["tags"] = tags
        place["budget_category"] = map_price_level(place.get("price_level"))
        place["kid_friendly"] = True
        place["pet_friendly"] = True
        place["wheelchair_accessible"] = True
        place["disclaimer"] = ""
    store_pois(user_input["location"], new_places)
    filtered_pois = get_filtered_pois(user_input)

# 🧭 Generate Itinerary
itinerary = generate_itinerary(
    filtered_pois,
    user_input["start_date"],
    user_input["end_date"],
    enable_hidden_gems=True
)

# 🆔 Save to Firestore
trip_id = str(uuid.uuid4())
store_itinerary(
    user_input["user_id"],
    user_input["location"],
    user_input["start_date"],
    user_input["end_date"],
    itinerary,
    trip_id
)
