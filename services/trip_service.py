from firebase_admin import db
import datetime
import math
import hashlib
import json
import asyncio
from schemas.trip_schema import TripCreate, Location
from services.map_service import calculate_route_with_osm, calculate_distance

# Trip creation caching system
_trip_cache = {}
_route_cache = {}
_location_cache = {}
_cache_locks = {}

def _get_cache_key(prefix: str, **kwargs) -> str:
    """Generate a consistent cache key for trip-related data"""
    # Sort kwargs to ensure consistent key generation
    sorted_params = sorted(kwargs.items())
    key_string = f"{prefix}:" + ":".join([f"{k}={v}" for k, v in sorted_params])
    return hashlib.md5(key_string.encode()).hexdigest()

def _get_route_cache_key(start_name: str, end_name: str, vehicle: str, preference: str = "fastest") -> str:
    """Generate cache key for route calculations"""
    return _get_cache_key("route", 
                         start=start_name.lower().strip(),
                         end=end_name.lower().strip(), 
                         vehicle=vehicle.lower(),
                         preference=preference.lower())

async def _get_cached_route(cache_key: str):
    """Get cached route from memory and Firebase"""
    # Check memory cache first
    if cache_key in _route_cache:
        cache_entry = _route_cache[cache_key]
        if datetime.datetime.now() < cache_entry['expires_at']:
            print(f"🎯 Route cache HIT (memory): {cache_key[:8]}...")
            return cache_entry['data']
        else:
            # Remove expired entry
            del _route_cache[cache_key]
    
    # Check Firebase cache
    try:
        cache_ref = db.reference(f'cache/routes/{cache_key}')
        cached_data = cache_ref.get()
        
        if cached_data:
            expires_at = datetime.datetime.fromisoformat(cached_data['expires_at'])
            if datetime.datetime.now() < expires_at:
                print(f"🎯 Route cache HIT (Firebase): {cache_key[:8]}...")
                # Store in memory cache for faster access
                _route_cache[cache_key] = {
                    'data': cached_data['data'],
                    'expires_at': expires_at
                }
                return cached_data['data']
            else:
                # Remove expired Firebase cache
                cache_ref.delete()
    except Exception as e:
        print(f"⚠️ Firebase cache read error: {e}")
    
    return None

async def _cache_route(cache_key: str, route_data: dict, hours: int = 24):
    """Cache route data in memory and Firebase"""
    expires_at = datetime.datetime.now() + datetime.timedelta(hours=hours)
    
    cache_entry = {
        'data': route_data,
        'expires_at': expires_at
    }
    
    # Store in memory cache
    _route_cache[cache_key] = cache_entry
    
    # Store in Firebase cache
    try:
        cache_ref = db.reference(f'cache/routes/{cache_key}')
        firebase_entry = {
            'data': route_data,
            'expires_at': expires_at.isoformat(),
            'created_at': datetime.datetime.now().isoformat()
        }
        cache_ref.set(firebase_entry)
        print(f"💾 Route cached: {cache_key[:8]}... (expires in {hours}h)")
    except Exception as e:
        print(f"⚠️ Firebase cache write error: {e}")

async def create_trip_for_user(trip_data: TripCreate, user_id: str, google_access_token: str = None):
    """
    Creates a new trip with intelligent caching and automatic Google Photos integration.
    If google_access_token is provided, automatically scans and populates photos.
    """
    try:
        # Step 1: Validate destinations
        if not trip_data.destinations or len(trip_data.destinations) == 0:
            route_info = {
                "status": "no_destinations",
                "total_distance_km": 0.0,
                "estimated_time_hours": 0.0,
                "message": "Trip created without route - no destinations specified",
                "routes": []
            }
        else:
            # Step 2: Cached route calculation
            route_info = await calculate_cached_route(
                start=trip_data.start_location,
                end=trip_data.destinations[0],
                vehicle=trip_data.vehicle_type,
                preference=getattr(trip_data, 'route_preference', 'fastest')
            )

        # Step 3: Prepare trip data
        data_to_save = {
            "title": trip_data.title,
            "duration_days": trip_data.duration_days,
            "start_location": {
                "name": trip_data.start_location.name,
                "lat": trip_data.start_location.lat,
                "lng": trip_data.start_location.lng
            },
            "destinations": [
                {
                    "name": dest.name,
                    "lat": dest.lat,
                    "lng": dest.lng
                } for dest in trip_data.destinations
            ],
            "vehicle_type": trip_data.vehicle_type,
            "start_date": trip_data.start_date,
            "preferences": trip_data.preferences or [],
            "user_id": user_id,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "route": route_info,
            "status": "active",
            "google_photos_enabled": google_access_token is not None
        }

        # Step 4: Save to Firebase
        trips_ref = db.reference('trips')
        new_trip_ref = trips_ref.push()
        new_trip_ref.set(data_to_save)

        # Step 5: Get trip ID and prepare response
        trip_id = new_trip_ref.key
        data_to_save['id'] = trip_id

        print(f"✅ Trip created: {trip_data.title} ({trip_data.start_location.name} → {trip_data.destinations[0].name})")

        # Step 6: 🔥 Automatic Google Photos Integration
        photo_sync_result = None
        if google_access_token:
            try:
                print(f"📸 Starting automatic photo scan for trip: {trip_id}")
                
                # Import here to avoid circular import
                from services import gphotos_service
                
                # Check if trip date is in the past (completed trip)
                start_date = datetime.date.fromisoformat(trip_data.start_date)
                end_date = start_date + datetime.timedelta(days=trip_data.duration_days)
                today = datetime.date.today()
                
                if end_date <= today:
                    # Trip is completed, do full photo sync
                    print(f"🎯 Trip appears completed, doing full photo sync")
                    photo_sync_result = await gphotos_service.sync_photos_for_completed_trip(
                        trip_id=trip_id,
                        user_id=user_id,
                        access_token=google_access_token
                    )
                else:
                    # Trip is upcoming or ongoing, just scan for now
                    print(f"📅 Trip is upcoming/ongoing, scanning for existing photos")
                    photo_scan = await gphotos_service.search_photos_by_trip(
                        access_token=google_access_token,
                        trip_id=trip_id,
                        user_id=user_id
                    )
                    photo_sync_result = {
                        "status": "scanned",
                        "photos_found": photo_scan.get("photos_found", 0),
                        "message": "Photos scanned, will auto-populate when trip is completed"
                    }
                
                # Update trip with photo sync status
                new_trip_ref.update({
                    "photos_initial_scan": True,
                    "photos_scan_timestamp": datetime.datetime.now().isoformat(),
                    "photos_found": photo_sync_result.get("photos_found", 0)
                })
                
                data_to_save['photos_sync_result'] = photo_sync_result
                
            except Exception as photo_error:
                print(f"⚠️ Photo sync failed (non-critical): {photo_error}")
                data_to_save['photos_sync_result'] = {
                    "status": "error",
                    "message": f"Photo sync failed: {str(photo_error)}"
                }

        return data_to_save

    except Exception as e:
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "user_id": user_id,
            "trip_title": getattr(trip_data, 'title', 'Unknown')
        }
        print(f"❌ Trip creation error: {error_details}")
        raise Exception(f"Failed to create trip: {str(e)}")

async def calculate_cached_route(start: Location, end: Location, vehicle: str = 'car', preference: str = 'fastest'):
    """
    Calculate route with intelligent caching system.
    Caches successful route calculations to speed up repeated requests.
    """
    # Generate cache key
    cache_key = _get_route_cache_key(start.name, end.name, vehicle, preference)
    
    # Check if we're already calculating this route (prevent duplicate API calls)
    if cache_key in _cache_locks:
        print(f"⏳ Route calculation already in progress: {start.name} → {end.name}")
        await _cache_locks[cache_key].wait()
        # Try to get the result that should now be cached
        cached_result = await _get_cached_route(cache_key)
        if cached_result:
            return cached_result
    
    # Check cache first
    cached_route = await _get_cached_route(cache_key)
    if cached_route:
        return cached_route
    
    # Create lock for this calculation
    _cache_locks[cache_key] = asyncio.Event()
    
    try:
        print(f"🔄 Calculating new route: {start.name} → {end.name} ({vehicle})")
        
        # Calculate new route
        route_result = await calculate_intelligent_route(start, end, vehicle, preference)
        
        # Cache successful results (don't cache errors)
        if route_result.get('status') in ['success', 'estimated']:
            await _cache_route(cache_key, route_result, hours=24)  # Cache for 24 hours
        
        return route_result
        
    finally:
        # Release lock and wake up waiting tasks
        _cache_locks[cache_key].set()
        del _cache_locks[cache_key]

async def calculate_intelligent_route(start: Location, end: Location, vehicle: str = 'car', preference: str = 'fastest'):
    """
    Intelligently calculates routes with fallback strategies for long distances.
    Handles OpenRouteService limitations dynamically.
    """
    try:
        # Step 1: Calculate straight-line distance to determine strategy
        distance_km = calculate_distance(start.lat, start.lng, end.lat, end.lng)
        
        print(f"🗺️ Route calculation: {start.name} → {end.name} ({distance_km:.1f}km)")
        
        # Step 2: Choose calculation strategy based on distance
        if distance_km <= 120:  # Well within ORS limits
            print("✅ Using precise OpenRouteService routing")
            routes = await calculate_route_with_osm(start, end, vehicle, preference)
            # Extract main route info for schema compliance
            main_route = routes[0] if routes else None
            return {
                "status": "success",
                "method": "openrouteservice",
                "total_distance_km": main_route["total_distance_km"] if main_route else distance_km,
                "estimated_time_hours": main_route["estimated_time_hours"] if main_route else distance_km / 50.0,
                "distance_km": distance_km,
                "routes": routes
            }
        
        elif distance_km <= 300:  # Try ORS but expect it might fail
            print("⚠️ Long distance - trying OpenRouteService with fallback")
            try:
                routes = await calculate_route_with_osm(start, end, vehicle, preference)
                # Extract main route info for schema compliance
                main_route = routes[0] if routes else None
                return {
                    "status": "success",
                    "method": "openrouteservice",
                    "total_distance_km": main_route["total_distance_km"] if main_route else distance_km,
                    "estimated_time_hours": main_route["estimated_time_hours"] if main_route else distance_km / 50.0,
                    "distance_km": distance_km,
                    "routes": routes
                }
            except Exception as ors_error:
                print(f"ORS failed as expected: {str(ors_error)[:100]}...")
                # Fall through to estimation method
        
        # Step 3: For very long distances, use intelligent estimation
        print("🧠 Using intelligent route estimation for long distance")
        estimated_route = await create_estimated_route(start, end, vehicle, distance_km)
        
        return {
            "status": "estimated",
            "method": "intelligent_estimation",
            "total_distance_km": round(distance_km, 1),
            "estimated_time_hours": estimated_route["estimated_time_hours"],
            "distance_km": distance_km,
            "routes": [estimated_route],
            "note": "Route estimated due to long distance. Actual route may vary."
        }

    except Exception as e:
        # Fallback to basic information with required schema fields
        distance_km = calculate_distance(start.lat, start.lng, end.lat, end.lng)
        # Estimate basic travel time (assuming 50 km/h average speed)
        estimated_hours = distance_km / 50.0
        
        return {
            "status": "basic",
            "method": "fallback",
            "total_distance_km": round(distance_km, 1),
            "estimated_time_hours": round(estimated_hours, 1),
            "distance_km": distance_km,  # Keep for backward compatibility
            "routes": [],
            "error": str(e),
            "note": "Unable to calculate detailed route. Basic trip information saved."
        }

async def create_estimated_route(start: Location, end: Location, vehicle: str, distance_km: float):
    """
    Creates an intelligent route estimation for long-distance trips.
    Uses Pakistani road network knowledge and realistic travel times.
    """
    # Realistic travel speeds by vehicle type in Pakistan
    speed_map = {
        'car': {
            'highway': 80,    # km/h on highways
            'city': 40,       # km/h in cities
            'mountain': 30    # km/h in mountain areas
        },
        'bike': {
            'highway': 70,
            'city': 35,
            'mountain': 25
        }
    }
    
    speeds = speed_map.get(vehicle, speed_map['car'])
    
    # Estimate route type based on locations and distance
    if distance_km > 500:
        # Long-distance highway travel
        avg_speed = speeds['highway'] * 0.8  # Account for stops, traffic
        route_type = "Long-distance highway route"
    elif distance_km > 200:
        # Mixed highway and regional roads
        avg_speed = speeds['highway'] * 0.7
        route_type = "Inter-city route"
    else:
        # Regional travel
        avg_speed = speeds['city'] * 1.2
        route_type = "Regional route"
    
    # Calculate estimated time
    estimated_hours = distance_km / avg_speed
    
    # Create simple straight-line geometry (Flutter can handle this)
    geometry = [
        [start.lng, start.lat],
        [end.lng, end.lat]
    ]
    
    return {
        "route_id": 0,
        "route_type": route_type,
        "total_distance_km": round(distance_km, 1),
        "estimated_time_hours": round(estimated_hours, 1),
        "geometry": geometry,
        "waypoints": [
            {"name": start.name, "lat": start.lat, "lng": start.lng},
            {"name": end.name, "lat": end.lat, "lng": end.lng}
        ],
        "estimation_details": {
            "method": "intelligent_estimation",
            "vehicle_type": vehicle,
            "avg_speed_kmh": round(avg_speed, 1),
            "note": "Estimated route - actual path may include intermediate cities and stops"
        }
    }

def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth.
    Returns distance in kilometers.
    """
    # Convert decimal degrees to radians
    lat1_rad = math.radians(lat1)
    lng1_rad = math.radians(lng1)
    lat2_rad = math.radians(lat2)
    lng2_rad = math.radians(lng2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlng = lng2_rad - lng1_rad
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in kilometers
    r = 6371
    return r * c

# Cache management functions
def get_cache_stats():
    """Get statistics about current cache usage"""
    return {
        "route_cache_size": len(_route_cache),
        "active_locks": len(_cache_locks),
        "cache_keys": list(_route_cache.keys())[:5]  # Show first 5 keys
    }

def clear_route_cache():
    """Clear all route caches"""
    global _route_cache
    _route_cache.clear()
    
    # Clear Firebase cache
    try:
        cache_ref = db.reference('cache/routes')
        cache_ref.delete()
        return {"message": "Route cache cleared successfully"}
    except Exception as e:
        return {"error": f"Failed to clear Firebase cache: {e}"}

# Keep existing functions but enhance them
def get_trips_for_user(user_id: str):
    """
    Retrieves all trips for a specific user from the Firebase Realtime Database.
    Completely dynamic - no hardcoded data.
    """
    try:
        trips_ref = db.reference('trips')
        user_trips = trips_ref.order_by_child('user_id').equal_to(user_id).get()

        if not user_trips:
            return []

        trips_list = []
        for trip_id, trip_data in user_trips.items():
            # Ensure all trips have consistent structure
            trip_data['id'] = trip_id
            
            # Add computed fields for Flutter
            if 'route' in trip_data and 'distance_km' in trip_data['route']:
                trip_data['computed_distance'] = trip_data['route']['distance_km']
            
            if 'destinations' in trip_data:
                trip_data['destination_count'] = len(trip_data['destinations'])
            
            trips_list.append(trip_data)
        
        # Sort by creation date (newest first)
        trips_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return trips_list

    except Exception as e:
        print(f"Error retrieving trips for user {user_id}: {e}")
        raise e

def get_trip_by_id(trip_id: str):
    """
    Retrieves a single trip by its unique ID.
    Enhanced with computed fields for Flutter integration.
    """
    try:
        trip_ref = db.reference(f'trips/{trip_id}')
        trip = trip_ref.get()

        if trip:
            trip['id'] = trip_id
            
            # Add computed fields for easy Flutter consumption
            if 'route' in trip and 'distance_km' in trip['route']:
                trip['computed_distance'] = trip['route']['distance_km']
                trip['has_route'] = len(trip['route'].get('routes', [])) > 0
            else:
                trip['computed_distance'] = 0
                trip['has_route'] = False
            
            if 'destinations' in trip:
                trip['destination_count'] = len(trip['destinations'])
                trip['destination_names'] = [dest['name'] for dest in trip['destinations']]
        
        return trip

    except Exception as e:
        print(f"Error retrieving trip {trip_id}: {e}")
        raise e 