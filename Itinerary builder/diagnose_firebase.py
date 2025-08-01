# diagnose_firebase.py
import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

print("🔍 Firebase Diagnostics - Comprehensive Project Scan")
print("=" * 60)

# Check credentials file
FIREBASE_SERVICE_ACCOUNT_PATH = "../credentials/lokpath-2d9a0-firebase-adminsdk-fbsvc-cd5812102d.json"

print(f"📁 Checking credentials file: {FIREBASE_SERVICE_ACCOUNT_PATH}")
if os.path.exists(FIREBASE_SERVICE_ACCOUNT_PATH):
    print("✅ Credentials file exists")
    
    # Read and display project info
    with open(FIREBASE_SERVICE_ACCOUNT_PATH, 'r') as f:
        creds_data = json.load(f)
    
    print(f"📊 Project ID: {creds_data.get('project_id')}")
    print(f"📧 Client Email: {creds_data.get('client_email')}")
    print(f"🔑 Client ID: {creds_data.get('client_id')}")
    
else:
    print("❌ Credentials file not found!")
    exit(1)

print("\n" + "=" * 60)

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)
    print("✅ Firebase initialized successfully")

db = firestore.client()

print(f"🔗 Connected to Firestore database")
print(f"📊 Firebase App Name: {firebase_admin.get_app().name}")

# Test 1: List ALL root collections
print("\n🔍 TEST 1: Scanning ALL root collections...")
try:
    all_collections = db.collections()
    collection_names = [col.id for col in all_collections]
    print(f"📊 Found {len(collection_names)} root collections:")
    for col_name in collection_names:
        print(f"   📁 {col_name}")
    
    if not collection_names:
        print("⚠️  NO ROOT COLLECTIONS FOUND!")
        print("💡 This indicates you're connected to an empty Firestore database")
    
except Exception as e:
    print(f"❌ Error listing collections: {e}")

# Test 2: Check if hidden_gems collection exists and has documents
print("\n🔍 TEST 2: Checking hidden_gems collection specifically...")
try:
    hidden_gems_ref = db.collection("hidden_gems")
    
    # Try to list documents in hidden_gems
    docs = list(hidden_gems_ref.list_documents())
    print(f"📊 Found {len(docs)} document references in hidden_gems:")
    
    for doc_ref in docs:
        print(f"   📄 Document: {doc_ref.id}")
        
        # Try to get the document
        try:
            doc = doc_ref.get()
            if doc.exists:
                print(f"      ✅ Document exists with data")
                data = doc.to_dict()
                if data:
                    print(f"      📋 Data keys: {list(data.keys())}")
                else:
                    print(f"      📝 Document exists but has no data")
            else:
                print(f"      ❌ Document reference exists but document is empty")
        except Exception as doc_e:
            print(f"      ❌ Error accessing document: {doc_e}")
        
        # Check for subcollections
        try:
            subcollections = doc_ref.collections()
            subcol_names = [col.id for col in subcollections]
            if subcol_names:
                print(f"      📁 Subcollections: {subcol_names}")
                
                # Check cities subcollection specifically
                if "cities" in subcol_names:
                    cities_ref = doc_ref.collection("cities")
                    city_docs = list(cities_ref.list_documents())
                    print(f"         🏙️  Cities: {[city.id for city in city_docs]}")
                    
                    # Check Bengaluru specifically
                    for city_doc in city_docs:
                        if city_doc.id.lower() in ["bengaluru", "bangalore"]:
                            print(f"         🎯 Found {city_doc.id}! Checking gems...")
                            
                            try:
                                gems_ref = city_doc.collection("gem_submissions")
                                gem_docs = list(gems_ref.stream())
                                print(f"            💎 Found {len(gem_docs)} gems")
                                
                                for gem_doc in gem_docs:
                                    gem_data = gem_doc.to_dict()
                                    print(f"               ✨ {gem_doc.id}: Status={gem_data.get('status')}, Tags={gem_data.get('tags')}")
                                    
                            except Exception as gem_e:
                                print(f"            ❌ Error accessing gems: {gem_e}")
            else:
                print(f"      📁 No subcollections found")
                
        except Exception as subcol_e:
            print(f"      ❌ Error checking subcollections: {subcol_e}")
    
    if not docs:
        print("⚠️  NO DOCUMENTS FOUND in hidden_gems collection")
        
except Exception as e:
    print(f"❌ Error checking hidden_gems collection: {e}")

# Test 3: Try the exact path we know should work
print("\n🔍 TEST 3: Direct access to known gem path...")
try:
    gem_ref = (db.collection("hidden_gems")
               .document("KA")
               .collection("cities")
               .document("Bengaluru")
               .collection("gem_submissions")
               .document("a700a743-7319-43c2-90a7-60c68ffd626f"))
    
    gem_doc = gem_ref.get()
    if gem_doc.exists:
        print("✅ SUCCESS! Found the gem via direct path")
        data = gem_doc.to_dict()
        print(f"   City: {data.get('city_name')}")
        print(f"   Status: {data.get('status')}")
        print(f"   Tags: {data.get('tags')}")
    else:
        print("❌ FAILED! Gem not found via direct path")
        print("💡 This confirms you're connected to a different database")
        
except Exception as e:
    print(f"❌ Error with direct access: {e}")

# Test 4: Compare with working test_firebase.py approach
print("\n🔍 TEST 4: Using exact same approach as test_firebase.py...")
try:
    # Reinitialize Firebase exactly like test_firebase.py
    if len(firebase_admin._apps) > 0:
        # Delete existing app and recreate
        firebase_admin.delete_app(firebase_admin.get_app())
    
    cred2 = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
    app2 = firebase_admin.initialize_app(cred2, name="test_app")
    db2 = firestore.client(app=app2)
    
    print("🔄 Reinitialized Firebase with new app instance")
    
    # Try the same direct access
    gem_ref2 = (db2.collection("hidden_gems")
                .document("KA")
                .collection("cities")
                .document("Bengaluru")
                .collection("gem_submissions")
                .document("a700a743-7319-43c2-90a7-60c68ffd626f"))
    
    gem_doc2 = gem_ref2.get()
    if gem_doc2.exists:
        print("✅ SUCCESS with new app instance!")
        data2 = gem_doc2.to_dict()
        print(f"   City: {data2.get('city_name')}")
        print(f"   Status: {data2.get('status')}")
        print(f"   Tags: {data2.get('tags')}")
    else:
        print("❌ STILL FAILED with new app instance")
        
except Exception as e:
    print(f"❌ Error with app reinitialize: {e}")

print("\n" + "=" * 60)
print("🏁 Firebase Diagnostics Complete")
print("=" * 60)

# Summary and recommendations
print("\n📋 SUMMARY:")
print("1. If TEST 1 shows 0 collections → You're connected to empty database")
print("2. If TEST 3 fails but test_firebase.py works → App initialization differs")
print("3. If all tests fail → Wrong project or credentials issue")
print("4. Check your Firebase console to verify which project you're looking at")
