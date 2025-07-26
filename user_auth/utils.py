# user_auth/utils.py
import firebase_admin
from firebase_admin import auth
from flask import request, abort, session, current_app
from functools import wraps

# Function to initialize Firebase Admin SDK (will be called from app.py)
def initialize_firebase_app(cred_path, storage_bucket=None):
    if not firebase_admin._apps: # Check if Firebase app is not already initialized
        cred = firebase_admin.credentials.Certificate(cred_path)
        if storage_bucket:
            firebase_admin.initialize_app(cred, {'storageBucket': storage_bucket})
        else:
            firebase_admin.initialize_app(cred)
    # You can access the initialized app via firebase_admin.get_app()

def verify_firebase_token(id_token):
    """
    Verifies a Firebase ID token.
    Returns the user's UID if valid, None otherwise.
    """
    try:
        # Verify the ID token
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        return uid
    except Exception as e:
        current_app.logger.error(f"Error verifying Firebase ID token: {e}")
        return None

def login_required_user(f):
    """
    Decorator for Flask routes to ensure a user is authenticated via Firebase ID token.
    Requires the client to send a 'Authorization: Bearer <id_token>' header.
    Stores the user's UID in the Flask session.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            abort(401, description="Authorization token missing.")

        if not auth_header.startswith("Bearer "):
            abort(401, description="Invalid Authorization header format. Expected 'Bearer <token>'.")

        id_token = auth_header.split(" ")[1] # Extract the token part

        uid = verify_firebase_token(id_token)
        if not uid:
            abort(401, description="Invalid or expired token.")

        # Store UID in session for easy access in the request lifecycle
        session['user_uid'] = uid
        return f(*args, **kwargs)
    return decorated_function