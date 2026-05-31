import firebase_admin
from firebase_admin import credentials, firestore

import os

json_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "instance", "smartestate-e98d5-firebase-adminsdk-fbsvc-e7676180b2.json")
db = None

if os.path.exists(json_path):
    cred = credentials.Certificate(json_path)
    
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
else:
    print(f"⚠️ Warning: Firebase certificate {json_path} not found. Firebase features will be disabled.")

def init_firebase_agents(firestore_db):
    if not firestore_db:
        return
    agents_to_add = ['surooh', 'omran', 'binthani', 'alhabeeb']
    agents_ref = firestore_db.collection('agents')
    
    try:
        existing = [doc.id for doc in agents_ref.stream()]
        for agent in agents_to_add:
            if agent not in existing:
                agents_ref.document(agent).set({
                    'email': f"{agent}@gmail.com",
                    'password': 'password123'
                })
                print(f"Added agent {agent} to Firebase")
    except Exception as e:
        print(f"Firebase agent init error: {e}")

init_firebase_agents(db)
