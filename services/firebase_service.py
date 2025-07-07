import firebase_admin
from firebase_admin import credentials, auth, db
import json

from core.config import settings

def initialize_firebase():
    """Initializes the Firebase Admin SDK."""
    try:
        # The service account key is expected to be a JSON string in the environment variable.
        service_account_info = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_KEY_JSON)
        
        cred = credentials.Certificate(service_account_info)
        
        firebase_admin.initialize_app(cred, {
            'databaseURL': settings.FIREBASE_DATABASE_URL
        })
        print("Firebase initialized successfully.")
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        # Depending on your app's needs, you might want to handle this more gracefully.
        # For now, we'll let the app continue, but auth features will fail.
        pass

# TODO: Add functions for creating and logging in users
def create_user_in_firebase(email, password, full_name):
    """Creates a user in Firebase Auth and stores details in Realtime DB."""
    try:
        # Create user in Firebase Authentication
        user_record = auth.create_user(
            email=email,
            password=password,
            display_name=full_name,
            email_verified=False  # You can send a verification email later
        )

        # Store additional user info in Realtime Database or Firestore
        # Using Realtime Database here as an example
        user_data = {
            'email': user_record.email,
            'full_name': full_name,
            'created_at': user_record.user_metadata.creation_timestamp
        }
        db.reference(f'users/{user_record.uid}').set(user_data)
        
        return {
            "uid": user_record.uid,
            "email": user_record.email,
            "full_name": user_record.display_name
        }

    except auth.EmailAlreadyExistsError:
        raise ValueError("The email address is already in use by another account.")
    except Exception as e:
        # Raise a generic exception for other potential errors
        raise e

# Call initialization on module load.
# This ensures Firebase is ready when the app starts.
initialize_firebase() 