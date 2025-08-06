import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
import sys

# ✅ Adjust path to import firebase
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from diary.firebase.firebase_config import db

# ✅ Local folder for uploads
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

# ✅ Check valid file extension
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ✅ Upload post handler
def upload_post(file, caption, user_uid, visibility="public"):
    if not file or not allowed_file(file.filename):
        raise ValueError("Invalid file or format. Allowed: png, jpg, jpeg, gif")

    filename = secure_filename(file.filename)
    file_ext = filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4()}.{file_ext}"
    filepath = os.path.join(UPLOAD_FOLDER, unique_name)

    # ✅ Save locally
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file.save(filepath)

    # ✅ Prepare Firestore post document
    post_id = str(uuid.uuid4())
    post_data = {
        "content": caption,
        "image_url": f"/{filepath}",
        "status": "approved" if visibility == "public" else "pending",
        "timestamp": datetime.utcnow().isoformat(),  # ✅ FIXED: use UTC
        "user_uid": user_uid
    }

    # ✅ Save to Firestore
    db.collection("community_posts").document(post_id).set(post_data)
    print(f"✅ Post created: {post_id}")
    return {"post_id": post_id, "image_url": post_data["image_url"]}


# ✅ Test block
if __name__ == "__main__":
    from werkzeug.datastructures import FileStorage

    # 🔸 Replace this path with an actual image on your system
    test_image_path = "sample_post.jpg"

    if not os.path.exists(test_image_path):
        print(f"❌ Test image '{test_image_path}' not found.")
    else:
        with open(test_image_path, "rb") as f:
            file = FileStorage(f, filename="sample_post.jpg")
            upload_post(file, "🔥 Test image from script", "test_user_uid")
