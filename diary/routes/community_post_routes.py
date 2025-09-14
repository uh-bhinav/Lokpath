from diary.firebase.firebase_config import db
from datetime import datetime
from firebase_admin import firestore

from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from diary.services.post_uploader import upload_post

from flask import Blueprint, jsonify, session, current_app
from firebase_admin import firestore
from user_auth.utils import login_required_user
from datetime import datetime, timezone


def create_community_post_bp(db):

    community_post_bp = Blueprint("community_post", __name__)

    @community_post_bp.route("/upload-post", methods=["POST"])
    def upload_post_route():
        try:
            if "file" not in request.files:
                return jsonify({"error": "No file part in request"}), 400
            
            file = request.files["file"]
            caption = request.form.get("caption", "")
            user_uid = request.form.get("user_uid", "")
            visibility = request.form.get("visibility", "public")

            if not user_uid or not caption:
                return jsonify({"error": "caption and user_uid are required"}), 400

            result = upload_post(file, caption, user_uid, visibility)
            return jsonify({"message": "Post created successfully", "data": result}), 200
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    @community_post_bp.route("/user-posts/<user_uid>", methods=["GET"])
    def get_posts_by_user(user_uid):
        try:
            posts_ref = db.collection("community_posts").where("user_uid", "==", user_uid)
            posts = posts_ref.stream()

            result = []
            for post in posts:
                data = post.to_dict()
                data["post_id"] = post.id
                result.append(data)

            return jsonify({"user_uid": user_uid, "posts": result}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    """@community_post_bp.route("/community-feed", methods=["GET"])
    def get_community_feed():
        try:
            limit = int(request.args.get("limit", 10))
            last_timestamp = request.args.get("last_timestamp")

            posts_ref = db.collection("community_posts").order_by("timestamp", direction="DESCENDING")

            if last_timestamp:
                last_timestamp_obj = datetime.fromisoformat(last_timestamp)
                posts_ref = posts_ref.start_after({"timestamp": last_timestamp_obj})

            posts = posts_ref.limit(limit).stream()

            result = []
            for post in posts:
                data = post.to_dict()
                data["post_id"] = post.id
                result.append(data)

            return jsonify({"posts": result}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500"""
    
    @community_post_bp.route("/community-feed", methods=["GET"])
    @login_required_user
    def get_personalized_community_feed():
        try:
            current_user_uid = session['user_uid']
            
            # --- Step 1: Fetch Current User's Data ---
            user_ref = db.collection('users').document(current_user_uid)
            user_doc = user_ref.get()
            if not user_doc.exists:
                return jsonify({"error": "User profile not found."}), 404
            
            user_data = user_doc.to_dict()
            user_interests = set(user_data.get('interests', []))
            
            following_ref = user_ref.collection('following')
            following_docs = following_ref.stream()
            following_ids = {doc.id for doc in following_docs}

            # --- Step 2: Fetch a Pool of Candidate Posts ---
            candidate_posts = {}

            # A) Get recent posts from people the user follows
            if following_ids:
                followed_posts_query = db.collection('community_posts').where('user_uid', 'in', list(following_ids)).order_by('timestamp', direction='DESCENDING').limit(50)
                for post in followed_posts_query.stream():
                    candidate_posts[post.id] = post.to_dict()

            # B) Get recent, popular posts for discovery
            discovery_query = db.collection('community_posts').order_by('like_count', direction='DESCENDING').limit(100)
            for post in discovery_query.stream():
                if post.id not in candidate_posts: # Avoid duplicates
                    candidate_posts[post.id] = post.to_dict()

            # --- Step 3: Score and Rank Each Post ---
            ranked_feed = []
            now = datetime.now(timezone.utc)

            for post_id, post_data in candidate_posts.items():
                score = 0.0
                post_author_uid = post_data.get('user_uid')
                
                # Signal 1: Relationship (Huge Boost)
                if post_author_uid in following_ids:
                    score += 1000

                # Signal 2: Engagement
                score += (post_data.get('like_count', 0) * 0.5)
                score += (post_data.get('comment_count', 0) * 1.0) # Comments are worth more

                # Signal 3: Interests (For Discovery Posts)
                if post_author_uid not in following_ids:
                    post_tags = set(post_data.get('tags', []))
                    interest_matches = len(user_interests.intersection(post_tags))
                    score += interest_matches * 50 # Big boost for each matching interest

                # Signal 4: Recency (Decay)
                post_timestamp_str = post_data.get('timestamp')
                if isinstance(post_timestamp_str, str):
                    post_timestamp = datetime.fromisoformat(post_timestamp_str)
                    hours_since_post = (now - post_timestamp).total_seconds() / 3600
                    # Penalize older posts
                    score /= (1 + hours_since_post / 24)
                else:
                    score = 0.1 

                post_data['post_id'] = post_id
                post_data['relevance_score'] = score
                ranked_feed.append(post_data)

            # --- Step 4: Sort by Final Score and Paginate ---
            final_feed = sorted(ranked_feed, key=lambda p: p['relevance_score'], reverse=True)
            
            page_limit = int(request.args.get("limit", 20))
            return jsonify({"posts": final_feed[:page_limit]}), 200

        except Exception as e:
            # Log the full error for debugging
            current_app.logger.error(f"Feed generation failed: {e}", exc_info=True)
            return jsonify({"error": "Could not generate feed."}), 500
    
    # --- Follow / Unfollow Logic ---
    @community_post_bp.route('/follow/<user_to_follow_id>', methods=['POST'])
    @login_required_user
    def follow_user(user_to_follow_id):
        current_user_uid = session['user_uid']
        if current_user_uid == user_to_follow_id:
            return jsonify({"error": "You cannot follow yourself."}), 400

        transaction = db.transaction()
        current_user_ref = db.collection('users').document(current_user_uid)
        followed_user_ref = db.collection('users').document(user_to_follow_id)
        following_ref = current_user_ref.collection('following').document(user_to_follow_id)
        follower_ref = followed_user_ref.collection('followers').document(current_user_uid)

        @firestore.transactional
        def update_in_transaction(tx):
            # --- START: CORRECTED CODE ---
            # 1. Check if already following by converting the result to a list
            following_doc_list = list(tx.get(following_ref))
            if not following_doc_list: # If the list is not empty, the document exists
                raise Exception("You are already following this user.")
            # --- END: CORRECTED CODE ---
            
            # 2. Add to 'following' list of current user
            tx.set(following_ref, {'followed_at': firestore.SERVER_TIMESTAMP})
            
            # 3. Add to 'followers' list of the other user
            tx.set(follower_ref, {'followed_at': firestore.SERVER_TIMESTAMP})

            # 4. Increment counts
            tx.update(current_user_ref, {'following_count': firestore.Increment(1)})
            tx.update(followed_user_ref, {'followers_count': firestore.Increment(1)})

        try:
            update_in_transaction(transaction)
            return jsonify({"message": f"Successfully followed user {user_to_follow_id}"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @community_post_bp.route('/unfollow/<user_to_unfollow_id>', methods=['POST'])
    @login_required_user
    def unfollow_user(user_to_unfollow_id):
        current_user_uid = session['user_uid']
        transaction = db.transaction()
        current_user_ref = db.collection('users').document(current_user_uid)
        unfollowed_user_ref = db.collection('users').document(user_to_unfollow_id)
        following_ref = current_user_ref.collection('following').document(user_to_unfollow_id)
        follower_ref = unfollowed_user_ref.collection('followers').document(current_user_uid)

        @firestore.transactional
        def update_in_transaction(tx):
            following_doc_list = list(tx.get(following_ref))
            if not following_doc_list: # If the list is empty, the document does not exists
                raise Exception("You are not following this user.")
            # --- END: CORRECTED CODE ---
            tx.delete(following_ref)
            tx.delete(follower_ref)
            tx.update(current_user_ref, {'following_count': firestore.Increment(-1)})
            tx.update(unfollowed_user_ref, {'followers_count': firestore.Increment(-1)})
            
        try:
            update_in_transaction(transaction)
            return jsonify({"message": f"Successfully unfollowed user {user_to_unfollow_id}"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    # --- Like / Unlike Logic ---
    @community_post_bp.route('/like/<post_id>', methods=['POST'])
    @login_required_user
    def like_post(post_id):
        current_user_uid = session['user_uid']
        transaction = db.transaction()
        user_ref = db.collection('users').document(current_user_uid)
        post_ref = db.collection('community_posts').document(post_id)
        liked_post_ref = user_ref.collection('liked_posts').document(post_id)

        @firestore.transactional
        def update_in_transaction(tx):
            like_doc_list = list(tx.get(liked_post_ref))
            if not like_doc_list: # If the list is not empty, the document exists
                raise Exception("You have already liked this post.")
            tx.set(liked_post_ref, {'liked_at': firestore.SERVER_TIMESTAMP})
            tx.update(post_ref, {'like_count': firestore.Increment(1)})
            tx.update(user_ref, {'liked_posts_count': firestore.Increment(1)})
        
        try:
            update_in_transaction(transaction)
            return jsonify({"message": f"Successfully liked post {post_id}"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @community_post_bp.route('/unlike/<post_id>', methods=['POST'])
    @login_required_user
    def unlike_post(post_id):
        current_user_uid = session['user_uid']
        transaction = db.transaction()
        user_ref = db.collection('users').document(current_user_uid)
        post_ref = db.collection('community_posts').document(post_id)
        liked_post_ref = user_ref.collection('liked_posts').document(post_id)

        @firestore.transactional
        def update_in_transaction(tx):
            unlike_doc_list = list(tx.get(liked_post_ref))
            if not unlike_doc_list: # If the list is not empty, the document exists
                raise Exception("You have not liked this post.")
            tx.delete(liked_post_ref)
            tx.update(post_ref, {'like_count': firestore.Increment(-1)})
            tx.update(user_ref, {'liked_posts_count': firestore.Increment(-1)})

        try:
            update_in_transaction(transaction)
            return jsonify({"message": f"Successfully unliked post {post_id}"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    # --- Save / Unsave Logic ---
    @community_post_bp.route('/save/<post_id>', methods=['POST'])
    @login_required_user
    def save_post(post_id):
        current_user_uid = session['user_uid']
        user_ref = db.collection('users').document(current_user_uid)
        saved_post_ref = user_ref.collection('saved_posts').document(post_id)

        if saved_post_ref.get().exists:
            return jsonify({"error": "You have already saved this post."}), 400
        
        saved_post_ref.set({'saved_at': firestore.SERVER_TIMESTAMP})
        return jsonify({"message": f"Successfully saved post {post_id}"}), 200

    @community_post_bp.route('/unsave/<post_id>', methods=['POST'])
    @login_required_user
    def unsave_post(post_id):
        current_user_uid = session['user_uid']
        user_ref = db.collection('users').document(current_user_uid)
        saved_post_ref = user_ref.collection('saved_posts').document(post_id)

        if not saved_post_ref.get().exists:
            return jsonify({"error": "You have not saved this post."}), 400
            
        saved_post_ref.delete()
        return jsonify({"message": f"Successfully unsaved post {post_id}"}), 200
    
    @community_post_bp.route('/posts/<post_id>/comment', methods=['POST'])
    @login_required_user
    def add_comment_to_post(post_id):
        """Adds a new comment to a specified post."""
        current_user_uid = session['user_uid']
        data = request.get_json()
        comment_text = data.get('text')

        if not comment_text:
            return jsonify({"error": "Comment text is required."}), 400

        try:
            post_ref = db.collection('community_posts').document(post_id)
            comments_ref = post_ref.collection('comments')
            
            # We need the user's name for the comment, let's fetch it
            user_info = db.collection('users').document(current_user_uid).get(['name', 'profile_image_url'])
            user_name = user_info.to_dict().get('name', 'Anonymous')
            user_photo = user_info.to_dict().get('profile_image_url', '')

            # Use a transaction to ensure comment count is updated atomically
            transaction = db.transaction()
            @firestore.transactional
            def update_in_transaction(tx):
                # Create the new comment document
                new_comment_ref = comments_ref.document()
                tx.set(new_comment_ref, {
                    'text': comment_text,
                    'user_uid': current_user_uid,
                    'user_name': user_name,
                    'user_photo': user_photo,
                    'timestamp': firestore.SERVER_TIMESTAMP
                })
                # Increment the comment count on the parent post
                tx.update(post_ref, {'comment_count': firestore.Increment(1)})
            
            update_in_transaction(transaction)
            return jsonify({"message": "Comment added successfully."}), 201

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    @community_post_bp.route('/posts/<post_id>/comments/<comment_id>', methods=['DELETE'])
    @login_required_user
    def delete_comment(post_id, comment_id):
        """Deletes a comment, ensuring the user is the author."""
        current_user_uid = session['user_uid']

        try:
            post_ref = db.collection('community_posts').document(post_id)
            comment_ref = post_ref.collection('comments').document(comment_id)
            
            comment_doc = comment_ref.get()
            if not comment_doc.exists:
                return jsonify({"error": "Comment not found."}), 404

            # Verify that the user deleting the comment is the one who wrote it
            if comment_doc.to_dict().get('user_uid') != current_user_uid:
                return jsonify({"error": "You are not authorized to delete this comment."}), 403

            # Use a transaction to ensure comment count is updated atomically
            transaction = db.transaction()
            @firestore.transactional
            def update_in_transaction(tx):
                tx.delete(comment_ref)
                tx.update(post_ref, {'comment_count': firestore.Increment(-1)})
            
            update_in_transaction(transaction)
            return jsonify({"message": "Comment deleted successfully."}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return community_post_bp

