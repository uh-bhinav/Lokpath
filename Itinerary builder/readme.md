# 🗺️ LokPath – AI Itinerary Builder (Backend Feature)

## 📌 Overview
This module powers the **AI-based itinerary generation** for LokPath. It:
- Fetches Places of Interest (POIs) dynamically using **Google Places API**.
- Scrapes Google reviews and tags POIs using **BERT zero-shot classification**.
- Filters POIs based on **budget, accessibility, kids/pets/disabilities**.
- Generates **multi-day itineraries** (up to two POIs per day by default) with rest logic and hidden gem placeholders.
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
    - Set `FIREBASE_SERVICE_ACCOUNT_PATH` environment variable to the path of this JSON file

### Environment Variables
- `FIREBASE_SERVICE_ACCOUNT_PATH` — absolute or relative path to your Firebase service account JSON. All scripts require this to connect to Firestore.

### 2️⃣ Python Environment
- Python 3.10 or above
- Virtual environment recommended (`venv`)

### 3️⃣ Dependencies (add to `requirements.txt`)


googlemaps
firebase-admin
requests
python-dotenv
transformers
torch
tqdm

yaml

Install these packages with:

```bash
pip install -r requirements.txt
```

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

All POIs are stored under `places/<location>/poi_list` where `<location>` is
always lowercased. `store_pois` and `get_filtered_pois` handle this
normalization automatically, so queries should use the same lowercase value.

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
    enable_hidden_gems=True,
    max_per_day=2
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
```

## 🗄️ Caching

`fetch_places()` and `get_reviews_for_place()` keep a small JSON cache in the
`cache/` directory. Cached entries are keyed by the request parameters so the
same lookup does not hit the Google API again. Remove the files in `cache/` to
force a refresh or set `use_cache=False` when calling either function.

---

## 📡 `/itinerary/generate` Route

Send a `POST` request with trip parameters to generate an itinerary. The server
uses the same logic as `run_pipeline.py` – it pulls POIs from Firestore, falls
back to Google Places when needed and returns the final multi‑day plan.

### Request Body

```json
{
  "user_id": "user_123",
  "location": "Bengaluru",
  "start_date": "2025-05-01",
  "end_date": "2025-05-07",
  "selected_interests": ["sunset", "romantic"],
  "budget": "low",
  "with_kids": true,
  "with_pets": false,
  "with_disabilities": false
}
```

### Response

```json
{
  "trip_id": "<uuid>",
  "itinerary": {
    "Day 1": [
      {
        "name": "POI name",
        "time_slot": "17:30–18:30",
        "tags": ["sunset"],
        "budget_category": "low",
        "disclaimer": "",
        "photo_url": "...",
        "coordinates": {"lat": 0, "lng": 0}
      },
      {
        "name": "Another POI",
        "time_slot": "14:00–16:00",
        "tags": ["shopping"],
        "budget_category": "low",
        "disclaimer": "",
        "photo_url": "...",
        "coordinates": {"lat": 0, "lng": 0}
      }
    ]
  }
}
```
