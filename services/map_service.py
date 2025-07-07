import httpx
from typing import List, Dict, Optional
from schemas.trip_schema import Location
from core.config import settings
import polyline
import traceback
import asyncio
import re
from firebase_admin import db
import json
import time
import math
from services import location_service



async def search_locations(query: str, country: str = "Pakistan") -> List[Dict]:
    """
    Search for locations using OpenRouteService geocoding API.
    Returns a list of location suggestions matching the query.
    Completely dynamic - no hardcoded locations.
    """
    if not query or len(query.strip()) < 2:
        return []
    
    api_key = settings.ORS_API_KEY
    if not api_key:
        raise ValueError("OpenRouteService API key is not configured.")

    url = "https://api.openrouteservice.org/geocode/search"
    
    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }
    
    params = {
        'text': query.strip(),
        'boundary.country': 'PK',  # Pakistan country code
        'size': 15,  # Get more results for better selection
        'layers': 'locality,region,neighbourhood,venue,address'  # Comprehensive search
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            
            locations = []
            seen_names = set()  # Avoid duplicates
            
            for feature in data.get('features', []):
                coords = feature.get('geometry', {}).get('coordinates', [])
                properties = feature.get('properties', {})
                
                if len(coords) >= 2 and properties.get('name'):
                    name = properties['name']
                    # Skip duplicates
                    if name.lower() in seen_names:
                        continue
                    seen_names.add(name.lower())
                    
                    # Build readable label
                    label_parts = [name]
                    if properties.get('region'):
                        label_parts.append(properties['region'])
                    if properties.get('country'):
                        label_parts.append(properties['country'])
                    
                    locations.append({
                        'name': name,
                        'label': ', '.join(label_parts),
                        'lat': coords[1],  # OpenRouteService returns [lng, lat]
                        'lng': coords[0],
                        'region': properties.get('region', ''),
                        'country': properties.get('country', 'Pakistan'),
                        'confidence': properties.get('confidence', 0.5)
                    })
            
            # Sort by confidence for better results
            locations.sort(key=lambda x: x['confidence'], reverse=True)
            return locations[:10]  # Return top 10 most relevant
            
        except httpx.HTTPStatusError as e:
            raise Exception(f"Error from OpenRouteService geocoding: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            print(f"!!! UNEXPECTED ERROR IN 'search_locations': {type(e).__name__} - {e}")
            traceback.print_exc()
            raise Exception(f"An unexpected error occurred during location search. Type: {type(e).__name__}, Details: {e}")

async def get_popular_locations() -> List[Dict]:
    """
    Get a list of popular Pakistani destinations dynamically.
    This can be enhanced to fetch from database or external sources.
    """
    return await location_service.get_popular_locations()

def get_coordinates_by_name(location_name: str, locations_list: List[Dict]) -> Optional[Location]:
    """
    Returns the coordinates for a given location name from a provided list.
    Supports fuzzy matching for better user experience.
    """
    if not location_name or not locations_list:
        return None
    
    location_name_lower = location_name.lower().strip()
    
    # Exact match first
    for location in locations_list:
        if location['name'].lower() == location_name_lower:
            return Location(
                name=location['name'],
                lat=location['lat'],
                lng=location['lng']
            )
    
    # Partial match second
    for location in locations_list:
        if location_name_lower in location['name'].lower() or location['name'].lower() in location_name_lower:
            return Location(
                name=location['name'],
                lat=location['lat'],
                lng=location['lng']
            )
    
    return None

def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth.
    Returns distance in kilometers.
    Uses the Haversine formula for accurate distance calculation.
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

async def calculate_route_with_osm(start: Location, end: Location, vehicle: str = 'car', route_preference: str = 'fastest'):
    """
    Calculates the route between two points using OpenRouteService.
    Enhanced with better error handling and distance checking.
    """
    # Check distance first to provide better error messages
    distance_km = calculate_distance(start.lat, start.lng, end.lat, end.lng)
    
    # Map our vehicle type to ORS profiles
    profile_map = {
        'car': 'driving-car',
        'bike': 'driving-motorcycle',
        'motorcycle': 'driving-motorcycle'
    }
    profile = profile_map.get(str(vehicle).lower(), 'driving-car')
    
    print(f"🗺️ ORS Route: {start.name} → {end.name} ({distance_km:.1f}km, {profile})")
    
    api_key = settings.ORS_API_KEY
    if not api_key:
        raise ValueError("OpenRouteService API key is not configured.")

    # Map route preferences to ORS options
    preference_map = {
        'fastest': 'fastest',
        'shortest': 'shortest', 
        'scenic': 'recommended'
    }
    
    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }
    
    body = {
        "coordinates": [
            [start.lng, start.lat],
            [end.lng, end.lat]
        ],
        "preference": preference_map.get(route_preference, 'fastest'),
        "alternative_routes": {
            "target_count": 2,  # Request alternatives
            "share_factor": 0.6,
            "weight_factor": 1.4
        },
        "radiuses": [-1, -1],  # Use closest road
        "continue_straight": False,
        "suppress_warnings": True
    }

    url = f"https://api.openrouteservice.org/v2/directions/{profile}/geojson"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=body, timeout=30.0)
            
            if response.status_code == 400:
                # Enhanced error handling for common issues
                error_data = response.json()
                error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                
                if 'distance' in error_msg.lower() or 'exceed' in error_msg.lower():
                    raise Exception(f"Route too long for OpenRouteService ({distance_km:.1f}km). Maximum supported distance is approximately 150km.")
                else:
                    raise Exception(f"OpenRouteService routing error: {error_msg}")
            
            response.raise_for_status()
            data = response.json()
            
            routes = []
            for i, feature in enumerate(data.get('features', [])):
                geometry = feature.get('geometry', {}).get('coordinates', [])
                properties = feature.get('properties', {})
                summary = properties.get('summary', {})
                
                if geometry and summary:
                    route = {
                        "route_id": i,
                        "route_type": f"Route {i+1}" if i > 0 else "Main Route",
                        "total_distance_km": round(summary.get('distance', 0) / 1000, 1),
                        "estimated_time_hours": round(summary.get('duration', 0) / 3600, 1),
                        "geometry": geometry,
                        "waypoints": [
                            {"name": start.name, "lat": start.lat, "lng": start.lng},
                            {"name": end.name, "lat": end.lat, "lng": end.lng}
                        ]
                    }
                    routes.append(route)
            
            if not routes:
                raise Exception("No valid routes found")
            
            print(f"✅ Found {len(routes)} route(s)")
            return routes
            
        except httpx.HTTPStatusError as e:
            error_msg = f"OpenRouteService HTTP error: {e.response.status_code}"
            try:
                error_data = e.response.json()
                if 'error' in error_data:
                    error_msg += f" - {error_data['error'].get('message', 'Unknown error')}"
            except:
                pass
            raise Exception(error_msg)
        except Exception as e:
            if "Route too long" in str(e):
                raise e  # Re-raise distance errors as-is
            print(f"!!! ROUTE CALCULATION ERROR: {type(e).__name__} - {e}")
            traceback.print_exc()
            raise Exception(f"Route calculation failed: {str(e)}")

async def find_stops_along_route(geometry: List[List[float]]):
    """
    Finds points of interest (POIs) along a route using the Overpass API.
    Focuses on stops that are actually on or very close to the route path.
    """
    overpass_url = "https://overpass-api.de/api/interpreter"

    # --- Improved Strategy: Use smaller radius and more frequent sampling ---
    # Sample every 50 points instead of 100 for better coverage
    sampled_points = geometry[::50]
    # Always include start and end points
    if len(geometry) > 0:
        sampled_points.insert(0, geometry[0])  # Add start
        if geometry[-1] not in sampled_points:
            sampled_points.append(geometry[-1])  # Add end

    # Build query parts with smaller 2km radius for more relevant results
    area_query_parts = []
    for lon, lat in sampled_points:
        area_query_parts.append(f"node(around:2000,{lat},{lon});")
    
    nodes_in_area_query = "".join(area_query_parts)

    # Enhanced query with more relevant categories for Pakistani tourism
    query = f"""
    [out:json][timeout:45];
    (
      {nodes_in_area_query}
    ) -> .nodes_in_area;
    (
      node.nodes_in_area["tourism"="attraction"];
      node.nodes_in_area["tourism"="viewpoint"];
      node.nodes_in_area["tourism"="museum"];
      node.nodes_in_area["tourism"="resort"];
      node.nodes_in_area["tourism"="hotel"];
      node.nodes_in_area["tourism"="guest_house"];
      node.nodes_in_area["historic"="monument"];
      node.nodes_in_area["historic"="fort"];
      node.nodes_in_area["historic"="castle"];
      node.nodes_in_area["natural"="peak"];
      node.nodes_in_area["natural"="waterfall"];
      node.nodes_in_area["natural"="lake"];
      node.nodes_in_area["natural"="hot_spring"];
      node.nodes_in_area["amenity"="restaurant"];
      node.nodes_in_area["amenity"="cafe"];
      node.nodes_in_area["amenity"="fuel"];
      node.nodes_in_area["amenity"="hospital"];
      node.nodes_in_area["leisure"="park"];
      node.nodes_in_area["place"="town"];
      node.nodes_in_area["place"="village"];
    );
    out body 100;
    >;
    out skel qt;
    """
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(overpass_url, data=query, timeout=45.0)
            response.raise_for_status()
            data = response.json()
            
            # --- Enhanced processing with categorization ---
            stops = {}
            priority_categories = {
                'tourism': ['attraction', 'viewpoint', 'museum', 'resort'],
                'historic': ['monument', 'fort', 'castle'],
                'natural': ['peak', 'waterfall', 'lake', 'hot_spring'],
                'place': ['town', 'village'],
                'amenity': ['restaurant', 'cafe', 'fuel', 'hospital'],
                'leisure': ['park']
            }
            
            for element in data.get("elements", []):
                if element.get("type") == "node" and element.get("tags"):
                    tags = element["tags"]
                    name = tags.get("name")
                    if name and len(name.strip()) > 0:
                        # Determine category and priority
                        category = "other"
                        priority = 3  # Lower number = higher priority
                        
                        for cat, subcats in priority_categories.items():
                            if cat in tags:
                                if tags[cat] in subcats:
                                    category = f"{cat}_{tags[cat]}"
                                    if cat in ['tourism', 'historic', 'natural']:
                                        priority = 1  # High priority
                                    elif cat == 'place':
                                        priority = 2  # Medium priority
                                    else:
                                        priority = 3  # Lower priority
                                    break
                        
                        # Use a composite key to handle duplicates but preserve the best one
                        key = name.lower().strip()
                        if key not in stops or stops[key]['priority'] > priority:
                            stops[key] = {
                                "name": name,
                                "lat": element.get("lat"),
                                "lng": element.get("lon"),
                                "category": category,
                                "priority": priority,
                                "tags": tags
                            }
            
            # Sort by priority and return top results
            sorted_stops = sorted(stops.values(), key=lambda x: (x['priority'], x['name']))
            return sorted_stops[:50]  # Return top 50 stops
            
        except httpx.HTTPStatusError as e:
            print(f"Error from Overpass API: {e.response.status_code} - {e.response.text}")
            traceback.print_exc()
            return []
        except Exception as e:
            print(f"!!! UNEXPECTED ERROR IN 'find_stops_along_route': {type(e).__name__} - {e}")
            traceback.print_exc()
            return [] 

async def calculate_route_with_llm(start_location: Location, end_location: Location, vehicle_type: str = 'car', route_preference: str = 'fastest'):
    """
    Calculates a route between two points using LLM-based route generation.
    Provides more contextual and accurate stops compared to the OSM-based approach.
    
    Args:
        start_location: Starting location object with name, lat, lng
        end_location: Destination location object with name, lat, lng
        vehicle_type: 'car' or 'bike'
        route_preference: 'fastest', 'shortest', or 'scenic'
        
    Returns:
        A list containing route information with suggested stops
    """
    from services.ai_service import generate_route_with_stops
    from firebase_admin import db
    import time
    import json
    
    try:
        print(f"Calculating LLM route from {start_location.name} to {end_location.name} by {vehicle_type}, preference: {route_preference}")
        
        # Generate a cache key for this route
        cache_key = f"route:{start_location.name.lower()}:{end_location.name.lower()}:{vehicle_type}:{route_preference}"
        
        # Check if we have a cached route
        try:
            route_ref = db.reference(f'route_cache/{cache_key}')
            cached_route = route_ref.get()
            
            if cached_route:
                # Check if the cache is still valid (30 days)
                cache_time = cached_route.get('timestamp', 0)
                current_time = int(time.time())
                
                if current_time - cache_time <= 30 * 24 * 60 * 60:  # 30 days in seconds
                    print(f"Using cached route for {start_location.name} to {end_location.name}")
                    return [cached_route['route_data']]
        except Exception as e:
            print(f"Error checking route cache: {e}")
            # Continue with generating a new route
        
        # No valid cache found, generate a new route
        route_data = await generate_route_with_stops(
            start_location=start_location.name,
            end_location=end_location.name,
            vehicle_type=vehicle_type,
            route_preference=route_preference
        )
        
        if not route_data:
            print("Warning: LLM returned empty route data")
            raise ValueError("Could not generate route information. Please try again.")
        
        # Extract route information with validation
        route_info = route_data.get("route_info", {})
        if not isinstance(route_info, dict):
            print(f"Warning: Invalid route_info format: {type(route_info)}")
            route_info = {}
            
        waypoints = route_data.get("waypoints", [])
        if not isinstance(waypoints, list):
            print(f"Warning: Invalid waypoints format: {type(waypoints)}")
            waypoints = []
            
        suggested_stops = route_data.get("suggested_stops", [])
        if not isinstance(suggested_stops, list):
            print(f"Warning: Invalid suggested_stops format: {type(suggested_stops)}")
            suggested_stops = []
        
        # Format the route info to match our existing API structure
        processed_route = {
            "route_id": 0,
            "route_type": "LLM Generated Route",
            "total_distance_km": route_info.get("total_distance_km", 0),
            "estimated_time_hours": route_info.get("estimated_time_hours", 0),
            "description": route_info.get("route_description", f"Route from {start_location.name} to {end_location.name}"),
            "waypoints": waypoints,
            "suggested_stops": suggested_stops
        }
        
        print(f"Successfully generated LLM route with {len(waypoints)} waypoints and {len(suggested_stops)} suggested stops")
        
        # Cache the route for future use
        try:
            cache_data = {
                'timestamp': int(time.time()),
                'route_data': processed_route
            }
            route_ref = db.reference(f'route_cache/{cache_key}')
            route_ref.set(cache_data)
            print(f"Route cached successfully: {cache_key}")
        except Exception as e:
            print(f"Error saving route to cache: {e}")
            # Continue even if caching fails
        
        # Return the route
        return [processed_route]
        
    except Exception as e:
        print(f"!!! ERROR IN 'calculate_route_with_llm': {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()
        raise Exception(f"An unexpected error occurred during LLM route calculation: {e}") 