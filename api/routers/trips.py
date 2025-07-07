from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict

# Import schemas, services, and security dependencies
from schemas.trip_schema import TripCreate, TripInfo, RouteCalculationRequest
from core.security import get_current_user
from services import trip_service, map_service

router = APIRouter(
    prefix="/trips",
    tags=["Trips"],
    responses={404: {"description": "Not found"}},
)

@router.post("/create", response_model=TripInfo)
async def create_trip(
    trip: TripCreate,
    google_access_token: str = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Creates a new trip plan with automatic Google Photos integration.
    
    - If google_access_token is provided, automatically scans Google Photos
    - For completed trips: Creates journal entries with photos immediately
    - For upcoming trips: Scans photos, populates journal when trip ends
    - Users don't need to manually upload photos anymore! 📸✨
    """
    try:
        user_id = current_user['uid']
        new_trip = await trip_service.create_trip_for_user(
            trip_data=trip, 
            user_id=user_id,
            google_access_token=google_access_token
        )
        return new_trip
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("", response_model=List[TripInfo])
async def get_user_trips(current_user: dict = Depends(get_current_user)):
    """
    Retrieves all trips for the currently authenticated user.
    """
    try:
        user_id = current_user['uid']
        trips = trip_service.get_trips_for_user(user_id=user_id)
        return trips
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/{trip_id}", response_model=TripInfo)
async def get_single_trip(
    trip_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves a single trip by its ID.
    Ensures the trip belongs to the currently authenticated user.
    """
    try:
        trip = trip_service.get_trip_by_id(trip_id=trip_id)
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")

        # Security check: Make sure the user requesting the trip is the one who owns it.
        if trip['user_id'] != current_user['uid']:
            raise HTTPException(status_code=403, detail="Not authorized to access this trip")
        
        return trip
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/locations/search")
async def search_locations(
    q: str = Query(..., description="Search query for locations")
):
    """
    Search for locations in Pakistan using the mapping service.
    """
    try:
        if len(q.strip()) < 2:
            raise HTTPException(status_code=400, detail="Search query must be at least 2 characters long")
        
        locations = await map_service.search_locations(q)
        return {"locations": locations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/locations/popular")
async def get_popular_locations():
    """
    Get a list of popular Pakistani destinations.
    """
    try:
        locations = await map_service.get_popular_locations()
        return {"locations": locations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.post("/route")
async def calculate_route(
    start_location_name: str = Query(..., description="Start location name"),
    end_location_name: str = Query(..., description="End location name"),
    vehicle_type: str = Query("car", description="Vehicle type: car or bike"),
    route_preference: str = Query("fastest", description="Route preference: fastest, shortest, or scenic")
):
    """
    Calculates a route with suggested stops between two locations using LLM-based generation.
    This provides contextually relevant stops with descriptions and visit time estimates.
    This endpoint does not require authentication for testing purposes.
    """
    try:
        # Log the request
        print(f"Processing route request: {start_location_name} to {end_location_name}, vehicle: {vehicle_type}, preference: {route_preference}")
        
        # Search for start location
        start_results = await map_service.search_locations(start_location_name)
        if not start_results:
            raise HTTPException(status_code=404, detail=f"Start location '{start_location_name}' not found")
        
        # Search for end location
        end_results = await map_service.search_locations(end_location_name)
        if not end_results:
            raise HTTPException(status_code=404, detail=f"End location '{end_location_name}' not found")
        
        # Use the first (most relevant) result for each
        start_coords = start_results[0]
        end_coords = end_results[0]
        
        # Create Location objects
        from schemas.trip_schema import Location
        start_location = Location(
            name=start_coords['name'],
            lat=start_coords['lat'],
            lng=start_coords['lng']
        )
        end_location = Location(
            name=end_coords['name'],
            lat=end_coords['lat'],
            lng=end_coords['lng']
        )
        
        # Calculate route with LLM
        routes = await map_service.calculate_route_with_llm(
            start_location=start_location,
            end_location=end_location,
            vehicle_type=vehicle_type,
            route_preference=route_preference
        )
        
        if not routes:
            raise HTTPException(status_code=500, detail="Could not generate route with LLM.")
        
        # Return the response
        return {
            "route": routes[0],
            "start_location": start_coords,
            "end_location": end_coords
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@router.get("/cache/stats")
async def get_cache_stats():
    """
    Get route cache statistics.
    """
    try:
        stats = trip_service.get_cache_stats()
        return {"cache_stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting cache stats: {e}")

@router.delete("/cache/routes")
async def clear_route_cache():
    """
    Clear route calculation cache.
    """
    try:
        result = trip_service.clear_route_cache()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {e}") 