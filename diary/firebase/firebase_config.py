import os
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# ✅ Load environment variables
load_dotenv()

# ✅ Initialize Firebase Admin SDK
if not firebase_admin._apps:
    # Get the directory of this file and look for credentials
    current_dir = os.path.dirname(os.path.abspath(__file__))
    default_cred_path = os.path.join(current_dir, "..", "credentials", "serviceAccountKey.json")
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", default_cred_path)
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

# ✅ Firestore client stays the same
db = firestore.client()

# ❌ No storage.bucket()
bucket = None  # We’ll use local fallback for images
