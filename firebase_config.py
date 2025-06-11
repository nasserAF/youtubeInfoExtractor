from firebase_admin import credentials, initialize_app, firestore, auth
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize Firebase Admin with your service account credentials
# Try to load credentials from environment variable (for Render)
firebase_creds_json = os.getenv('FIREBASE_CREDENTIALS_JSON')

if firebase_creds_json:
    import json
    cred_dict = json.loads(firebase_creds_json)
    cred = credentials.Certificate(cred_dict)
else:
    # Fallback to local file (for local development)
    cred = credentials.Certificate("serviceAccountKey.json")

# Initialize Firebase app if not already initialized
if not firebase_admin._apps:
    app = initialize_app(cred)
else:
    app = firebase_admin.get_app()

# Get Firestore client and constants
db = firestore.client()
SERVER_TIMESTAMP = firestore.SERVER_TIMESTAMP

# Get Auth client
auth_client = auth
