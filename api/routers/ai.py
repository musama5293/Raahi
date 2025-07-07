from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import db
import datetime

from schemas.ai_schema import (
    HotspotGenerateRequest, HotspotInfo,
    BlogGenerateRequest, BlogInfo,
    TripSuggestionRequest, TripSuggestionResponse,
    ComprehensiveTripRequest, ComprehensiveTripPlan
)
from services.ai_service import (
    generate_and_save_daily_hotspot, generate_and_save_trip_blog,
    generate_trip_suggestion, get_user_daily_hotspot,
    get_cached_hotspot_info, clear_hotspot_cache, force_regenerate_daily_hotspot_pool,
    generate_comprehensive_trip_plan
)
from core.security import get_current_user

router = APIRouter(
    prefix="/ai",
    tags=["AI Features"],
    responses={404: {"description": "Not found"}},
)

@router.post("/hotspot/generate", response_model=HotspotInfo)
async def generate_hotspot(
    request: HotspotGenerateRequest,
    current_user: dict = Depends(get_current_user) # For now, any user can trigger it
):
    """
    (Admin) Generates and saves the daily hotspot.
    In a real app, this would be a protected admin-only endpoint or a scheduled job.
    """
    try:
        hotspot = await generate_and_save_daily_hotspot(
            place_name=request.place_name,
            region=request.region
        )
        return hotspot
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hotspot/today", response_model=HotspotInfo)
async def get_today_hotspot(current_user: dict = Depends(get_current_user)):
    """
    Gets today's personalized hotspot for the current user.
    Each user sees a different destination from the daily pool, ensuring variety.
    The same user will always see the same hotspot on the same day.
    """
    try:
        user_id = current_user['uid']
        hotspot = await get_user_daily_hotspot(user_id)
        return hotspot
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/hotspot/generate-auto")
async def generate_automatic_hotspot(current_user: dict = Depends(get_current_user)):
    """
    Gets today's personalized hotspot for the current user (same as GET endpoint).
    This endpoint is kept for backward compatibility.
    Uses the new user-specific assignment system.
    """
    try:
        user_id = current_user['uid']
        hotspot = await get_user_daily_hotspot(user_id)
        return hotspot
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/hotspot/force-regenerate")
async def force_regenerate_hotspot(current_user: dict = Depends(get_current_user)):
    """
    ADMIN ONLY: Forces regeneration of today's entire hotspot pool.
    This affects all users and should only be used by administrators.
    """
    try:
        # TODO: Add admin permission check here
        # if not is_admin(current_user):
        #     raise HTTPException(status_code=403, detail="Admin access required")
        
        pool = await force_regenerate_daily_hotspot_pool()
        return {
            "message": "Hotspot pool regenerated successfully",
            "hotspots_generated": len(pool),
            "date": datetime.date.today().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hotspot/cache-info")
async def get_cache_info(current_user: dict = Depends(get_current_user)):
    """
    ADMIN ONLY: Returns information about the current hotspot cache state.
    Useful for debugging and monitoring.
    """
    try:
        # TODO: Add admin permission check here
        # if not is_admin(current_user):
        #     raise HTTPException(status_code=403, detail="Admin access required")
        
        cache_info = await get_cached_hotspot_info()
        return cache_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/hotspot/cache")
async def clear_cache(
    date: str = None,
    current_user: dict = Depends(get_current_user)
):
    """
    ADMIN ONLY: Clears the hotspot cache.
    If date is provided (YYYY-MM-DD), clears only that date.
    If no date provided, clears all cache.
    """
    try:
        # TODO: Add admin permission check here
        # if not is_admin(current_user):
        #     raise HTTPException(status_code=403, detail="Admin access required")
        
        await clear_hotspot_cache(date)
        message = f"Cache cleared for {date}" if date else "All cache cleared"
        return {"message": message}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/blog/generate", response_model=BlogInfo)
async def generate_blog(
    request: BlogGenerateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Generates a travel blog for one of the user's trips.
    """
    try:
        user_id = current_user['uid']
        blog = await generate_and_save_trip_blog(
            trip_id=request.trip_id,
            user_id=user_id,
            tone=request.tone
        )
        return blog
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/suggest-trip", response_model=TripSuggestionResponse)
async def suggest_trip(
    request: TripSuggestionRequest
):
    """
    Generates a personalized trip suggestion based on user preferences.
    """
    try:
        suggestion = await generate_trip_suggestion(request)
        return suggestion
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/plan-trip", response_model=ComprehensiveTripPlan)
async def plan_comprehensive_trip(
    request: ComprehensiveTripRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Generates a comprehensive, personalized trip plan based on user requirements.
    """
    try:
        user_id = current_user['uid']
        plan = await generate_comprehensive_trip_plan(request, user_id)
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ADMIN ONLY ENDPOINTS - Remove these in production or add proper admin authentication

@router.post("/hotspot/generate")
async def generate_manual_hotspot(
    request: HotspotGenerateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    ADMIN ONLY: Manual hotspot generation.
    This endpoint should be restricted to admin users in production.
    Regular users should only use the automatic system.
    """
    try:
        # TODO: Add admin permission check here
        # if not is_admin(current_user):
        #     raise HTTPException(status_code=403, detail="Admin access required")
        
        hotspot = await generate_and_save_daily_hotspot(
            place_name=request.place_name,
            region=request.region
        )
        return hotspot
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 