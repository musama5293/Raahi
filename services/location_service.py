import httpx
from typing import List, Dict, Optional, Tuple
from schemas.trip_schema import Location
from core.config import settings
import traceback
import asyncio
from firebase_admin import db
import json
import time

# Dictionary of common Pakistani locations with their correct spellings and coordinates
# This helps handle spelling variations and ensures we can find important locations
COMMON_PAKISTANI_LOCATIONS = {
    "islamabad": {"name": "Islamabad", "lat": 33.7219, "lng": 73.0433, "region": "Islamabad", "country": "Pakistan"},
    "karachi": {"name": "Karachi", "lat": 24.8607, "lng": 67.0011, "region": "Sindh", "country": "Pakistan"},
    "lahore": {"name": "Lahore", "lat": 31.5204, "lng": 74.3587, "region": "Punjab", "country": "Pakistan"},
    "peshawar": {"name": "Peshawar", "lat": 34.0151, "lng": 71.5249, "region": "Khyber Pakhtunkhwa", "country": "Pakistan"},
    "quetta": {"name": "Quetta", "lat": 30.1798, "lng": 66.9750, "region": "Balochistan", "country": "Pakistan"},
    "multan": {"name": "Multan", "lat": 30.1575, "lng": 71.5249, "region": "Punjab", "country": "Pakistan"},
    "faisalabad": {"name": "Faisalabad", "lat": 31.4504, "lng": 73.1350, "region": "Punjab", "country": "Pakistan"},
    "rawalpindi": {"name": "Rawalpindi", "lat": 33.5651, "lng": 73.0169, "region": "Punjab", "country": "Pakistan"},
    "gujranwala": {"name": "Gujranwala", "lat": 32.1877, "lng": 74.1945, "region": "Punjab", "country": "Pakistan"},
    "sialkot": {"name": "Sialkot", "lat": 32.4945, "lng": 74.5229, "region": "Punjab", "country": "Pakistan"},
    "abbottabad": {"name": "Abbottabad", "lat": 34.1558, "lng": 73.2194, "region": "Khyber Pakhtunkhwa", "country": "Pakistan"},
    "murree": {"name": "Murree", "lat": 33.9071, "lng": 73.3943, "region": "Punjab", "country": "Pakistan"},
    "muree": {"name": "Murree", "lat": 33.9071, "lng": 73.3943, "region": "Punjab", "country": "Pakistan"},  # Common misspelling
    "nathiagali": {"name": "Nathiagali", "lat": 34.0651, "lng": 73.3903, "region": "Khyber Pakhtunkhwa", "country": "Pakistan"},
    "hunza": {"name": "Hunza", "lat": 36.3128, "lng": 74.6439, "region": "Gilgit-Baltistan", "country": "Pakistan"},
    "skardu": {"name": "Skardu", "lat": 35.2927, "lng": 75.6376, "region": "Gilgit-Baltistan", "country": "Pakistan"},
    "gilgit": {"name": "Gilgit", "lat": 35.9221, "lng": 74.3087, "region": "Gilgit-Baltistan", "country": "Pakistan"},
    "swat": {"name": "Swat", "lat": 34.7700, "lng": 72.3600, "region": "Khyber Pakhtunkhwa", "country": "Pakistan"},
    "kalam": {"name": "Kalam", "lat": 35.5308, "lng": 72.5846, "region": "Khyber Pakhtunkhwa", "country": "Pakistan"},
    "naran": {"name": "Naran", "lat": 34.9044, "lng": 73.6644, "region": "Khyber Pakhtunkhwa", "country": "Pakistan"},
    "kaghan": {"name": "Kaghan", "lat": 34.7778, "lng": 73.5333, "region": "Khyber Pakhtunkhwa", "country": "Pakistan"},
    "fairy meadows": {"name": "Fairy Meadows", "lat": 35.3888, "lng": 74.5763, "region": "Gilgit-Baltistan", "country": "Pakistan"},
    "chitral": {"name": "Chitral", "lat": 35.8511, "lng": 71.7842, "region": "Khyber Pakhtunkhwa", "country": "Pakistan"},
    "kalash": {"name": "Kalash Valley", "lat": 35.6869, "lng": 71.6692, "region": "Khyber Pakhtunkhwa", "country": "Pakistan"},
    "gwadar": {"name": "Gwadar", "lat": 25.1264, "lng": 62.3225, "region": "Balochistan", "country": "Pakistan"},
    "hyderabad": {"name": "Hyderabad", "lat": 25.3960, "lng": 68.3578, "region": "Sindh", "country": "Pakistan"},
    "sukkur": {"name": "Sukkur", "lat": 27.7052, "lng": 68.8570, "region": "Sindh", "country": "Pakistan"},
    "larkana": {"name": "Larkana", "lat": 27.5598, "lng": 68.2264, "region": "Sindh", "country": "Pakistan"},
    "bahawalpur": {"name": "Bahawalpur", "lat": 29.3956, "lng": 71.6722, "region": "Punjab", "country": "Pakistan"},
    "muzaffarabad": {"name": "Muzaffarabad", "lat": 34.3565, "lng": 73.4713, "region": "Azad Kashmir", "country": "Pakistan"}
}

async def search_locations(query: str, country: str = "Pakistan") -> List[Dict]:
    """
    Search for locations using a combination of local data and OpenRouteService.
    First checks against common Pakistani locations, then uses the API if needed.
    """
    # Clean the query and convert to lowercase for matching
    clean_query = query.strip().lower()
    
    # Check if the query matches any common Pakistani location
    if clean_query in COMMON_PAKISTANI_LOCATIONS:
        location_data = COMMON_PAKISTANI_LOCATIONS[clean_query]
        return [{
            'name': location_data['name'],
            'label': f"{location_data['name']}, {location_data['region']}, {location_data['country']}",
            'lat': location_data['lat'],
            'lng': location_data['lng'],
            'region': location_data['region'],
            'country': location_data['country']
        }]
    
    # Check for partial matches in common locations
    partial_matches = []
    for key, location_data in COMMON_PAKISTANI_LOCATIONS.items():
        if clean_query in key or key in clean_query:
            partial_matches.append({
                'name': location_data['name'],
                'label': f"{location_data['name']}, {location_data['region']}, {location_data['country']}",
                'lat': location_data['lat'],
                'lng': location_data['lng'],
                'region': location_data['region'],
                'country': location_data['country']
            })
    
    # If we found partial matches, return them
    if partial_matches:
        return partial_matches
    
    # Otherwise, use the OpenRouteService API
    api_key = settings.ORS_API_KEY
    if not api_key:
        raise ValueError("OpenRouteService API key is not configured.")

    url = "https://api.openrouteservice.org/geocode/search"
    
    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }
    
    params = {
        'text': query,
        'boundary.country': 'PK',  # Pakistan country code
        'size': 10,  # Limit to 10 results
        'layers': 'locality,region,country'  # Focus on cities, regions
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            
            locations = []
            for feature in data.get('features', []):
                coords = feature.get('geometry', {}).get('coordinates', [])
                properties = feature.get('properties', {})
                
                if len(coords) >= 2 and properties.get('name'):
                    locations.append({
                        'name': properties['name'],
                        'label': properties.get('label', properties['name']),
                        'lat': coords[1],  # OpenRouteService returns [lng, lat]
                        'lng': coords[0],
                        'region': properties.get('region', ''),
                        'country': properties.get('country', '')
                    })
            
            return locations
            
        except httpx.HTTPStatusError as e:
            raise Exception(f"Error from OpenRouteService geocoding: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            # Add detailed logging to diagnose the issue
            print(f"!!! UNEXPECTED ERROR IN 'search_locations': {type(e).__name__} - {e}")
            traceback.print_exc()
            raise Exception(f"An unexpected error occurred during location search. Type: {type(e).__name__}, Details: {e}")

def get_route_cache_key(start_location: str, end_location: str, vehicle_type: str, route_preference: str) -> str:
    """
    Generate a cache key for route data based on start, end, vehicle type, and preference.
    """
    # Normalize location names to lowercase for consistent keys
    start_norm = start_location.lower().strip()
    end_norm = end_location.lower().strip()
    
    # Create a consistent key format
    return f"route:{start_norm}:{end_norm}:{vehicle_type}:{route_preference}"

async def get_cached_route(start_location: str, end_location: str, vehicle_type: str, route_preference: str) -> Dict:
    """
    Try to get a route from the cache.
    Returns None if not found or expired.
    """
    try:
        cache_key = get_route_cache_key(start_location, end_location, vehicle_type, route_preference)
        route_ref = db.reference(f'route_cache/{cache_key}')
        route_data = route_ref.get()
        
        if not route_data:
            return None
            
        # Check if the cache is still valid (30 days)
        cache_time = route_data.get('cache_time', 0)
        current_time = int(time.time())
        
        if current_time - cache_time > 30 * 24 * 60 * 60:  # 30 days in seconds
            return None
            
        return route_data.get('route_data')
    except Exception as e:
        print(f"Error retrieving cached route: {e}")
        return None

async def save_route_to_cache(start_location: str, end_location: str, vehicle_type: str, 
                             route_preference: str, route_data: Dict) -> None:
    """
    Save a route to the cache.
    """
    try:
        cache_key = get_route_cache_key(start_location, end_location, vehicle_type, route_preference)
        route_ref = db.reference(f'route_cache/{cache_key}')
        
        cache_data = {
            'cache_time': int(time.time()),
            'route_data': route_data
        }
        
        route_ref.set(cache_data)
        print(f"Route cached successfully: {cache_key}")
    except Exception as e:
        print(f"Error saving route to cache: {e}")

async def get_popular_locations() -> List[Dict]:
    """
    Get a list of popular Pakistani destinations from our predefined list.
    """
    popular_places = [
        "Islamabad", "Karachi", "Lahore", "Peshawar", "Faisalabad", 
        "Hunza", "Skardu", "Murree", "Swat", "Naran", "Fairy Meadows"
    ]
    
    results = []
    for place in popular_places:
        place_data = COMMON_PAKISTANI_LOCATIONS.get(place.lower())
        if place_data:
            results.append({
                'name': place_data['name'],
                'label': f"{place_data['name']}, {place_data['region']}, {place_data['country']}",
                'lat': place_data['lat'],
                'lng': place_data['lng'],
                'region': place_data['region'],
                'country': place_data['country']
            })
    
    return results 