# LokPath Diary Backend - Complete Implementation

## 🎯 Overview
A comprehensive backend service for travel diary functionality that supports photo uploads (JPG/HEIC), GPS extraction, EXIF timestamp processing, and location-based timeline organization.

## 🏗️ Architecture

### Firestore Structure
```
/diary/{user_id}/itineraries/{trip_id}/photos/{photo_id}
```

### Photo Document Schema
```json
{
  "photo_id": "uuid-string",
  "url": "/uploads/diary_photos/user_123/trip_id/photo_id.jpg",
  "caption": "User provided caption",
  "timestamp": "2025-08-05T07:47:15.415626",
  "exif_timestamp": "2025-08-05T07:47:15.415626",
  "upload_timestamp": "2025-08-05T08:00:00.123456",
  "gps": {
    "lat": 12.222725,
    "lng": 75.6500638888889
  },
  "has_gps": true,
  "file_type": "HEIC"
}
```

## 🚀 Features Implemented

### 1. Multi-Format Photo Support
- **JPG/JPEG**: Standard EXIF extraction via `exifread`
- **HEIC/HEIF**: Triple fallback method:
  1. PIL direct EXIF extraction
  2. exifread on HEIC files  
  3. Convert to JPEG and re-extract

### 2. GPS Data Extraction
- Automatic GPS coordinate extraction from EXIF data
- Handles both Northern/Southern and Eastern/Western hemispheres
- Converts DMS (Degrees, Minutes, Seconds) to decimal degrees
- Graceful handling of photos without GPS data

### 3. Timestamp Management
- **EXIF Timestamp**: Original photo capture time from camera
- **Upload Timestamp**: When photo was uploaded to server
- **Final Timestamp**: Uses EXIF time if available, falls back to upload time
- Supports timeline sorting by actual photo capture time

### 4. Comprehensive API Endpoints

#### Photo Management
- `POST /user-itinerary/{user_id}/{trip_id}/upload-photo`
- `GET /user-itinerary/{user_id}/{trip_id}/photos`
- `DELETE /user-itinerary/{user_id}/{trip_id}/photos/{photo_id}`

#### Timeline & Organization
- `GET /user-itinerary/{user_id}/{trip_id}/timeline` - Daily grouped timeline
- `GET /user-itinerary/{user_id}/{trip_id}/locations` - Location-based clustering
- `GET /user-itinerary/{user_id}/{trip_id}/stats` - Trip statistics

#### Itinerary Management
- `PUT /user-itinerary/{user_id}/{trip_id}` - Update itinerary
- `DELETE /user-itinerary/{user_id}/{trip_id}` - Delete itinerary + all photos

## 📂 File Structure
```
diary/
├── main.py                           # Flask app entry point
├── requirements.txt                  # Python dependencies
├── test_diary_api.py                # API testing script
├── routes/
│   └── diary_routes.py              # All diary-related endpoints
├── services/
│   ├── diary_photo_uploader.py      # Photo processing & EXIF extraction
│   └── firestore_photo_storage.py   # Firestore CRUD operations
├── firebase/
│   └── firebase_config.py           # Firebase initialization
└── uploads/diary_photos/             # File storage structure
    └── {user_id}/
        └── {trip_id}/
            └── {photo_id}.{ext}
```

## 🧪 Testing

### cURL Commands
```bash
# Upload Photo
curl -X POST http://127.0.0.1:5000/user-itinerary/user_123/07c2f0d4/upload-photo \
  -F "file=@/path/to/photo.HEIC" \
  -F "caption=Sunset from the peak"

# Get Timeline
curl -X GET http://127.0.0.1:5000/user-itinerary/user_123/07c2f0d4/timeline

# Get Location Summary
curl -X GET http://127.0.0.1:5000/user-itinerary/user_123/07c2f0d4/locations

# Get Trip Stats
curl -X GET http://127.0.0.1:5000/user-itinerary/user_123/07c2f0d4/stats
```

### Python Test Script
```bash
python test_diary_api.py
```

## 📊 Response Examples

### Timeline Response
```json
{
  "trip_id": "07c2f0d4",
  "user_id": "user_123",
  "photo_count": 5,
  "photos_with_gps": 3,
  "photos_without_gps": 2,
  "daily_timeline": {
    "2025-08-05": [
      {
        "photo_id": "abc123",
        "caption": "Morning view",
        "url": "/uploads/diary_photos/user_123/07c2f0d4/abc123.jpg",
        "timestamp": "2025-08-05T07:47:15.415626",
        "gps": {"lat": 12.222725, "lng": 75.6500638888889},
        "has_gps": true,
        "file_type": "HEIC"
      }
    ]
  }
}
```

### Location Summary Response
```json
{
  "trip_id": "07c2f0d4",
  "total_locations": 3,
  "total_geotagged_photos": 8,
  "locations": [
    {
      "lat": 12.223,
      "lng": 75.650,
      "photo_count": 4,
      "representative": {
        "photo_id": "abc123",
        "caption": "Beach sunset",
        "timestamp": "2025-08-05T18:30:00"
      }
    }
  ]
}
```

## 🔧 Dependencies
- **Flask 2.3.3**: Web framework
- **firebase-admin**: Firestore integration
- **Pillow 10.0.1**: Image processing
- **pillow-heif 0.13.0**: HEIC file support
- **ExifRead 3.0.0**: EXIF data extraction
- **python-dateutil**: Date/time parsing

## 🚦 Setup Instructions

1. **Environment Setup**
   ```bash
   # Use your existing virtual environment in itinerary_builder folder
   cd ../itinerary_builder
   source venv/bin/activate  # or your venv activation command
   cd ../diary
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Firebase Configuration**
   - Ensure `firebase/firebase_config.py` has correct Firebase setup
   - Place your service account key in `credentials/serviceAccountKey.json`

4. **Run the Server**
   ```bash
   python main.py
   ```

## ✅ What's Working

1. **✅ File Type Support**: JPG, JPEG, HEIC, HEIF with proper EXIF extraction
2. **✅ GPS Extraction**: Triple fallback method ensures maximum GPS recovery
3. **✅ Timeline Sorting**: Uses actual photo capture time when available
4. **✅ Firestore Integration**: Structured data storage with proper schema
5. **✅ Location Clustering**: Groups photos by approximate location for mapping
6. **✅ Comprehensive Stats**: Photo counts, GPS availability, file type breakdown
7. **✅ Error Handling**: Graceful handling of photos without GPS/timestamps
8. **✅ File Organization**: Clean directory structure by user and trip

## 🎯 Ready for Frontend Integration
The backend is now complete and ready for frontend integration. All endpoints return consistent JSON responses with proper error handling and comprehensive metadata for building rich travel diary experiences.


Here’s a **detailed summary** of the LokPath Diary backend features, with specific implementations and file responsibilities:

---

## 🗂️ **Diary Feature Overview**

The LokPath Diary backend enables users to upload travel photos, extract and store metadata (GPS, timestamps, captions), organize photos by trip, and retrieve them via a RESTful API. It supports both JPEG and HEIC formats, robust EXIF extraction, and integrates with Firebase Firestore for persistent storage.

---

### 1. **main.py**
- **Purpose:** Flask app entry point.
- **Key Implementations:**
  - Registers all route blueprints (`proximity_bp`, `community_post_bp`, `progress_bp`, `diary_bp`).
  - Serves uploaded images via `/uploads/<filename>`.
  - Provides a `/user-itinerary/<user_id>/diary-feed` endpoint for aggregated photo feeds.
  - Handles app startup and debug mode.

---

### 2. **diary_routes.py**
- **Purpose:** Core diary API endpoints (grouped by trip).
- **Key Implementations:**
  - **PUT/DELETE `/user-itinerary/<user_id>/<trip_id>`:** Update or delete trip itineraries and all associated photos.
  - **POST `/user-itinerary/<user_id>/<trip_id>/upload-photo`:** Handles photo uploads, calls `upload_diary_photo`, returns metadata.
  - **GET `/user-itinerary/<user_id>/<trip_id>/photos`:** Lists all photos for a trip.
  - **GET `/user-itinerary/<user_id>/<trip_id>/timeline`:** Returns a daily-grouped timeline of photos, sorted by capture time.
  - **GET `/user-itinerary/<user_id>/<trip_id>/locations`:** Clusters photos by GPS for mapping.
  - **GET `/user-itinerary/<user_id>/<trip_id>/stats`:** Returns trip statistics (photo count, GPS coverage, file types, date range).
  - **DELETE `/user-itinerary/<user_id>/<trip_id>/photos/<photo_id>`:** Deletes a specific photo and its metadata.

---

### 3. **user_itinerary_routes.py**
- **Purpose:** Alternate diary endpoints (similar to diary_routes.py).
- **Key Implementations:**
  - Handles saving, deleting, uploading, and retrieving photos for user itineraries.
  - Stores photo metadata in a `diary_photos` subcollection in Firestore.
  - Implements `/timeline` endpoint for chronological photo retrieval.

---

### 4. **proximity_routes.py**
- **Purpose:** Itinerary optimization endpoints.
- **Key Implementations:**
  - **POST `/optimize-itinerary`:** Calls `optimize_itinerary_by_proximity` to reorder trip POIs (points of interest) using clustering and nearest-neighbor logic.

---

### 5. **community_post_routes.py**
- **Purpose:** Community feed and post upload endpoints.
- **Key Implementations:**
  - **POST `/upload-post`:** Handles image post uploads (with captions, visibility).
  - **GET `/user-posts/<user_uid>`:** Fetches all posts by a user.
  - **GET `/community-feed`:** Returns a paginated, timestamp-sorted feed of community posts.

---

### 6. **progress_routes.py**
- **Purpose:** Itinerary creation and retrieval endpoints.
- **Key Implementations:**
  - **POST `/save-itinerary`:** Saves a new itinerary for a user.
  - **GET `/user-itineraries/<user_id>`:** Lists all itineraries for a user.
  - **GET `/user-itinerary/<user_id>/<trip_id>`:** Retrieves a specific itinerary.

---

### 7. **diary_photo_uploader.py**
- **Purpose:** Handles photo upload, EXIF extraction, and metadata assembly.
- **Key Implementations:**
  - **File Saving:** Uses `secure_filename` and UUIDs for unique photo storage.
  - **EXIF Extraction:** Triple fallback for GPS/timestamp:
    1. PIL direct EXIF from HEIC.
    2. ExifRead on HEIC.
    3. Convert HEIC to JPEG, then extract EXIF.
  - **GPS Parsing:** Converts DMS to decimal, handles hemisphere signs.
  - **Metadata:** Assembles all info (`photo_id`, `url`, `caption`, `timestamp`, `exif_timestamp`, `gps`, `file_type`, `has_gps`).
  - **Firestore Integration:** Calls `save_photo_to_firestore` to persist metadata.

---

### 8. **firestore_photo_storage.py**
- **Purpose:** Firestore CRUD operations for photo metadata.
- **Key Implementations:**
  - **save_photo_to_firestore:** Stores photo metadata under `/diary/{user_id}/itineraries/{trip_id}/photos/{photo_id}`.
  - **get_photos_from_firestore:** Retrieves all photos for a trip, sorted by timestamp.
  - **delete_photo_from_firestore:** Deletes a photo’s metadata.

---

### 9. **proximity_optimizer.py**
- **Purpose:** Optimizes itinerary POI order for efficient travel.
- **Key Implementations:**
  - **Haversine Distance:** Calculates distance between coordinates.
  - **order_by_proximity:** Greedy nearest-neighbor TSP for POI ordering.
  - **optimize_itinerary_by_proximity:** Clusters POIs by day using KMeans, reorders within clusters, updates Firestore.

---

### 10. **post_uploader.py**
- **Purpose:** Handles community post uploads.
- **Key Implementations:**
  - **allowed_file:** Validates image file types.
  - **upload_post:** Saves image locally, stores post metadata in Firestore.

---

### 11. **firebase_config.py**
- **Purpose:** Firebase Admin SDK initialization.
- **Key Implementations:**
  - Loads credentials from environment or file.
  - Initializes Firestore client (`db`).

---

### 12. **requirements.txt**
- **Purpose:** Lists all Python dependencies.
- **Key Implementations:**
  - Flask, Pillow, pillow-heif, ExifRead, firebase-admin, python-dateutil, scikit-learn, numpy, etc.

---

### 13. **README.md**
- **Purpose:** Documentation.
- **Key Implementations:**
  - Explains architecture, Firestore schema, API endpoints, features, setup instructions, and sample responses.

---

## 📦 **File Storage Structure**
- **Uploads:** `/uploads/diary_photos/{user_id}/{trip_id}/{photo_id}.{ext}`

---

## 🔑 **Key Features Implemented**
- Multi-format photo upload (JPG/HEIC)
- Robust EXIF GPS/timestamp extraction
- Unique photo IDs and secure filenames
- Firestore-based metadata storage
- Timeline and location-based retrieval
- Trip and photo CRUD operations
- Community feed and post uploads
- Itinerary optimization (clustering + TSP)
- Comprehensive API documentation

---

**In summary:**  
The diary backend is modular, extensible, and production-ready, supporting rich travel diary features with robust metadata handling, efficient storage, and flexible retrieval for both personal and community use. Each file is focused on a specific aspect of the system, ensuring clean separation of concerns and maintainability.