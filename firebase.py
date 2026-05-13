import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("smartestate-e98d5-firebase-adminsdk-fbsvc-e7676180b2.json")
# Prevent multiple app initializations if imported multiple times
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

def init_firebase_agents(firestore_db):
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