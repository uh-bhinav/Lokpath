# diary/firebase/firebase_config.py
import os
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# Load environment variables from the root .env file
load_dotenv()

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    # Standardized path finding: looks for an environment variable first,
    # then falls back to the root credentials folder.
    cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")

    if not cred_path:
        # Build path relative to this file to find the root directory
        # __file__ -> firebase_config.py
        # os.path.dirname -> /diary/firebase
        # .parents[2] -> /
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        cred_path = os.path.join(project_root, "credentials", "lokpath-2d9a0-firebase-adminsdk-fbsvc-cd5812102d.json")

    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"Firebase service account key not found at path: {cred_path}. Ensure the path is correct or set FIREBASE_SERVICE_ACCOUNT_PATH.")

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

# Firestore client
db = firestore.client()

# This is no longer needed as the main app.py initialization handles the bucket
bucket = None