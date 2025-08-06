import os
import uuid
import datetime
import exifread
from werkzeug.utils import secure_filename
from pillow_heif import register_heif_opener
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from dateutil import parser as date_parser
from diary.services.firestore_photo_storage import save_photo_to_firestore
register_heif_opener()

def convert_heic_to_jpeg(heic_path, jpeg_path):
    """Convert HEIC to JPEG while preserving EXIF data"""
    image = Image.open(heic_path)
    
    # Extract EXIF data from original image
    exif_data = image.getexif()
    
    # Save with EXIF data preserved
    if exif_data:
        image.save(jpeg_path, format="JPEG", exif=exif_data)
    else:
        image.save(jpeg_path, format="JPEG")

def extract_gps_from_heic(heic_path):
    """Extract GPS data directly from HEIC file using PIL"""
    try:
        image = Image.open(heic_path)
        exif_data = image.getexif()
        
        if not exif_data:
            print("No EXIF data found in HEIC file")
            return None
            
        # Get GPS info from EXIF
        gps_info = {}
        for tag_id in exif_data:
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                gps_data = exif_data[tag_id]
                for gps_tag_id in gps_data:
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_info[gps_tag] = gps_data[gps_tag_id]
                break
        
        if not gps_info:
            print("No GPS info found in EXIF data")
            return None
        
        print(f"Found GPS tags: {list(gps_info.keys())}")
        
        if 'GPSLatitude' in gps_info and 'GPSLongitude' in gps_info:
            def convert_to_degrees(gps_coord):
                """Convert GPS coordinates to decimal degrees"""
                if isinstance(gps_coord, (list, tuple)) and len(gps_coord) >= 3:
                    d, m, s = gps_coord[:3]
                    return float(d) + (float(m) / 60.0) + (float(s) / 3600.0)
                return float(gps_coord)
            
            lat = convert_to_degrees(gps_info['GPSLatitude'])
            if gps_info.get('GPSLatitudeRef') == 'S':
                lat = -lat
                
            lng = convert_to_degrees(gps_info['GPSLongitude'])
            if gps_info.get('GPSLongitudeRef') == 'W':
                lng = -lng
                
            return {"lat": lat, "lng": lng}
        else:
            print(f"Missing required GPS fields. Available: {list(gps_info.keys())}")
            
    except Exception as e:
        print(f"GPS extraction from HEIC error: {e}")
    
    return None

def extract_gps_from_heic_exifread(heic_path):
    """Alternative method: Try to extract GPS from HEIC using exifread directly"""
    try:
        with open(heic_path, 'rb') as f:
            # Some versions of exifread can handle HEIC files directly
            tags = exifread.process_file(f, stop_tag="GPS GPSLongitude")

            gps_lat = tags.get("GPS GPSLatitude")
            gps_lat_ref = tags.get("GPS GPSLatitudeRef")
            gps_lng = tags.get("GPS GPSLongitude")
            gps_lng_ref = tags.get("GPS GPSLongitudeRef")

            if gps_lat and gps_lat_ref and gps_lng and gps_lng_ref:
                def convert_to_degrees(gps):
                    d, m, s = [float(x.num) / float(x.den) for x in gps.values]
                    return d + (m / 60.0) + (s / 3600.0)

                lat = convert_to_degrees(gps_lat)
                if gps_lat_ref.values[0] != "N":
                    lat = -lat

                lng = convert_to_degrees(gps_lng)
                if gps_lng_ref.values[0] != "E":
                    lng = -lng

                return {"lat": lat, "lng": lng}
    except Exception as e:
        print(f"GPS extraction from HEIC using exifread error: {e}")
    return None

def extract_datetime_from_exif(file_path):
    """Extract photo capture datetime from EXIF data"""
    try:
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, stop_tag="EXIF DateTimeOriginal")

            # Try different datetime tags in order of preference
            datetime_original = tags.get("EXIF DateTimeOriginal")
            datetime_tag = tags.get("EXIF DateTime")
            datetime_digitized = tags.get("EXIF DateTimeDigitized")

            exif_datetime = datetime_original or datetime_tag or datetime_digitized

            if exif_datetime:
                # Convert EXIF datetime format to ISO format
                dt_str = str(exif_datetime)
                # EXIF format: "2025:08:05 07:47:15"
                dt = datetime.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                return dt.isoformat()
                
    except Exception as e:
        print(f"EXIF datetime extraction error: {e}")
    
    return None

def extract_datetime_from_heic(heic_path):
    """Extract datetime from HEIC file using PIL"""
    try:
        image = Image.open(heic_path)
        exif_data = image.getexif()
        
        if not exif_data:
            return None
            
        # Look for datetime in EXIF
        for tag_id in exif_data:
            tag = TAGS.get(tag_id, tag_id)
            if tag in ["DateTime", "DateTimeOriginal", "DateTimeDigitized"]:
                dt_str = exif_data[tag_id]
                try:
                    # EXIF format: "2025:08:05 07:47:15"
                    dt = datetime.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                    return dt.isoformat()
                except:
                    continue
                    
    except Exception as e:
        print(f"HEIC datetime extraction error: {e}")
    
    return None

UPLOAD_DIR = "uploads/diary_photos"

def _extract_gps(file_path):
    try:
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, stop_tag="GPS GPSLongitude")

            gps_lat = tags.get("GPS GPSLatitude")
            gps_lat_ref = tags.get("GPS GPSLatitudeRef")
            gps_lng = tags.get("GPS GPSLongitude")
            gps_lng_ref = tags.get("GPS GPSLongitudeRef")

            if gps_lat and gps_lat_ref and gps_lng and gps_lng_ref:
                def convert_to_degrees(gps):
                    d, m, s = [float(x.num) / float(x.den) for x in gps.values]
                    return d + (m / 60.0) + (s / 3600.0)

                lat = convert_to_degrees(gps_lat)
                if gps_lat_ref.values[0] != "N":
                    lat = -lat

                lng = convert_to_degrees(gps_lng)
                if gps_lng_ref.values[0] != "E":
                    lng = -lng

                return {"lat": lat, "lng": lng}
    except Exception as e:
        print(f"GPS extraction error: {e}")
    return None


def upload_diary_photo(file, user_id, trip_id, caption):
    photo_id = str(uuid.uuid4())
    filename = secure_filename(file.filename)
    file_ext = filename.split(".")[-1].lower()
    new_filename = f"{photo_id}.{file_ext}"

    photo_path = os.path.join(UPLOAD_DIR, user_id, trip_id)
    os.makedirs(photo_path, exist_ok=True)

    full_path = os.path.join(photo_path, new_filename)
    file.save(full_path)

    gps_info = None
    exif_timestamp = None

    # ✅ Enhanced HEIC GPS extraction with multiple fallback methods
    if file.filename.lower().endswith((".heic", ".heif")):
        print(f"📱 Processing HEIC file: {filename}")
        
        # Extract EXIF timestamp from HEIC
        print("📅 Extracting EXIF timestamp from HEIC...")
        exif_timestamp = extract_datetime_from_heic(full_path)
        if exif_timestamp:
            print(f"✅ EXIF timestamp found: {exif_timestamp}")
        else:
            print("❌ No EXIF timestamp found in HEIC")
        
        # Method 1: Extract GPS directly from HEIC using PIL
        print("🔍 Trying Method 1: PIL direct EXIF extraction...")
        gps_info = extract_gps_from_heic(full_path)
        if gps_info:
            print(f"✅ Method 1 success: {gps_info}")
        
        # Method 2: Try exifread directly on HEIC
        if not gps_info:
            print("🔍 Trying Method 2: exifread direct on HEIC...")
            gps_info = extract_gps_from_heic_exifread(full_path)
            if gps_info:
                print(f"✅ Method 2 success: {gps_info}")
        
        # Method 3: Convert to JPEG and extract (preserving EXIF)
        if not gps_info or not exif_timestamp:
            print("🔍 Trying Method 3: Convert to JPEG then extract...")
            temp_jpeg_path = full_path.replace(".HEIC", ".jpg").replace(".heic", ".jpg").replace(".HEIF", ".jpg").replace(".heif", ".jpg")
            convert_heic_to_jpeg(full_path, temp_jpeg_path)
            
            if not gps_info:
                gps_info = _extract_gps(temp_jpeg_path)
                if gps_info:
                    print(f"✅ Method 3 GPS success: {gps_info}")
                else:
                    print("❌ Method 3 failed - no GPS found in converted JPEG")
            
            if not exif_timestamp:
                exif_timestamp = extract_datetime_from_exif(temp_jpeg_path)
                if exif_timestamp:
                    print(f"✅ Method 3 timestamp success: {exif_timestamp}")
            
            os.remove(temp_jpeg_path)
        
        if not gps_info:
            print("⚠️ All GPS extraction methods failed for HEIC file")
    else:
        # For regular JPG/JPEG files
        print(f"📸 Processing regular image file: {filename}")
        
        # Extract EXIF timestamp
        print("📅 Extracting EXIF timestamp from image...")
        exif_timestamp = extract_datetime_from_exif(full_path)
        if exif_timestamp:
            print(f"✅ EXIF timestamp found: {exif_timestamp}")
        else:
            print("❌ No EXIF timestamp found")
        
        # Extract GPS
        gps_info = _extract_gps(full_path)
        if gps_info:
            print(f"✅ GPS extracted from regular image: {gps_info}")
        else:
            print("❌ No GPS found in regular image")

    # Use EXIF timestamp if available, otherwise use current time
    final_timestamp = exif_timestamp or datetime.datetime.utcnow().isoformat()
    
    photo_data = {
        "url": f"/{full_path}",
        "caption": caption,
        "timestamp": final_timestamp,
        "exif_timestamp": exif_timestamp,  # Store both for reference
        "upload_timestamp": datetime.datetime.utcnow().isoformat(),
        "gps": gps_info,
        "has_gps": gps_info is not None,
        "file_type": file_ext.upper(),
        "photo_id": photo_id
    }

    # 🔥 Store in Firestore
    save_photo_to_firestore(user_id, trip_id, photo_id, photo_data)

    return {
        "url": f"/{full_path}",
        "caption": caption,
        "timestamp": final_timestamp,
        "gps": gps_info,
        "file_type": file_ext.upper(),
        "exif_timestamp": exif_timestamp,
        "upload_timestamp": datetime.datetime.utcnow().isoformat(),
        "has_gps": gps_info is not None,
        "photo_id": photo_id
    }