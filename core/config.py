import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Application settings and configuration."""
    # TODO: Add your Firebase service account key JSON here
    FIREBASE_SERVICE_ACCOUNT_KEY_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY_JSON")
    
    # TODO: Add your Firebase Realtime Database URL here if you use it
    FIREBASE_DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL")

    # External APIs
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
    TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
    
    # We will use OpenRouteService for directions, which is based on OpenStreetMap
    # You can get a free key from https://openrouteservice.org/
    ORS_API_KEY = os.getenv("ORS_API_KEY")

settings = Settings() 