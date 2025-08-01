# test_firebase.py
import firebase_admin
from firebase_admin import credentials, firestore
import os

print("🔍 Testing Firebase connection...")

# Initialize Firebase
FIREBASE_SERVICE_ACCOUNT_PATH = "../credentials/lokpath-2d9a0-firebase-adminsdk-fbsvc-cd5812102d.json"

if not firebase_admin._apps:
    if os.path.exists(FIREBASE_SERVICE_ACCOUNT_PATH):
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized successfully")
    else:
        print(f"❌ Firebase credentials not found at: {FIREBASE_SERVICE_ACCOUNT_PATH}")
        exit(1)

db = firestore.client()

print("\n🔍 Testing direct access to your specific gem...")

# Direct path to your gem
gem_path = "hidden_gems/KA/cities/Bengaluru/gem_submissions/a700a743-7319-43c2-90a7-60c68ffd626f"
print(f"📍 Accessing: {gem_path}")

try:
    gem_ref = (db.collection("hidden_gems")
               .document("KA")
               .collection("cities")
               .document("Bengaluru")
               .collection("gem_submissions")
               .document("a700a743-7319-43c2-90a7-60c68ffd626f"))

    gem_doc = gem_ref.get()

    if gem_doc.exists:
        print("✅ Found your gem!")
        data = gem_doc.to_dict()
        print(f"   City: {data.get('city_name')}")
        print(f"   Status: {data.get('status')}")
        print(f"   Tags: {data.get('tags')}")
        print(f"   Description: {data.get('description', '')[:100]}...")
        
        # Test if tags match user interests
        user_interests = ['family-friendly', 'adventurous', 'peaceful', 'cultural']
        gem_tags = data.get('tags', [])
        
        user_tags = set(tag.lower() for tag in user_interests)
        gem_tags_lower = set(tag.lower() for tag in gem_tags)
        
        intersection = user_tags.intersection(gem_tags_lower)
        print(f"   Tag intersection: {intersection}")
        
        if intersection:
            print("   ✅ This gem should match user interests!")
        else:
            print("   ❌ This gem doesn't match user interests")
    else:
        print("❌ Gem not found at expected path")

except Exception as e:
    print(f"❌ Error accessing gem: {e}")
    import traceback
    traceback.print_exc()

print("\n🔍 Testing collection queries...")

try:
    # Test querying with status filter
    gems_ref = (db.collection("hidden_gems")
                .document("KA")
                .collection("cities")
                .document("Bengaluru")
                .collection("gem_submissions"))

    verified_gems = list(gems_ref.where("status", "==", "verified").stream())
    print(f"📊 Found {len(verified_gems)} verified gems")

    pending_gems = list(gems_ref.where("status", "==", "pending_review").stream())
    print(f"📊 Found {len(pending_gems)} pending_review gems")

    # List all gems regardless of status
    all_gems = list(gems_ref.stream())
    print(f"📊 Found {len(all_gems)} total gems")
    
    for gem_doc in all_gems:
        data = gem_doc.to_dict()
        print(f"   ✨ {gem_doc.id}: Status={data.get('status')}, Tags={data.get('tags')}")

except Exception as e:
    print(f"❌ Error querying gems: {e}")
    import traceback
    traceback.print_exc()

print("\n🔍 Testing state and city structure...")

try:
    # Check if KA state document exists
    ka_ref = db.collection("hidden_gems").document("KA")
    ka_doc = ka_ref.get()
    
    if ka_doc.exists:
        print("✅ KA state document exists")
        
        # Check cities collection
        cities_ref = ka_ref.collection("cities")
        city_docs = list(cities_ref.list_documents())
        print(f"📍 Found {len(city_docs)} city documents:")
        
        for city_ref in city_docs:
            print(f"   🏙️ {city_ref.id}")
            
            # Check gem count in each city
            try:
                gems_in_city = list(city_ref.collection("gem_submissions").stream())
                print(f"      💎 {len(gems_in_city)} gems")
            except Exception as gem_e:
                print(f"      ❌ Error counting gems: {gem_e}")
    else:
        print("❌ KA state document doesn't exist")
        
        # Try to list all state documents
        states = list(db.collection("hidden_gems").list_documents())
        print(f"🏛️ Available states: {[state.id for state in states]}")

except Exception as e:
    print(f"❌ Error checking structure: {e}")
    import traceback
    traceback.print_exc()

print("\n✅ Firebase test completed!")
