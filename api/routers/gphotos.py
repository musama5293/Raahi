from fastapi import APIRouter, Depends, HTTPException
from schemas.gphotos_schema import GPhotosScanRequest, GPhotosScanResponse
from schemas.user_schema import UserInfo
from core.security import get_current_user
from services import gphotos_service

router = APIRouter(
    prefix="/gphotos",
    tags=["Google Photos Integration"],
    responses={404: {"description": "Not found"}},
)

@router.post("/scan", response_model=GPhotosScanResponse)
async def scan_google_photos(
    request: GPhotosScanRequest,
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Enhanced photo scanning with intelligent caching and photo processing.
    Automatically finds and processes photos from the trip timeframe.
    """
    try:
        results = await gphotos_service.search_photos_by_trip(
            access_token=request.access_token,
            trip_id=request.trip_id,
            user_id=current_user['uid']
        )
        return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred during the photo scan.")

@router.post("/auto-populate/{trip_id}")
async def auto_populate_trip_photos(
    trip_id: str,
    access_token: str,
    current_user: UserInfo = Depends(get_current_user)
):
    """
    🔥 NEW: Automatically populate journal entries with photos from Google Photos.
    This is the magic feature that makes photos appear without user upload!
    
    Called after trip creation or when user wants to sync photos.
    """
    try:
        result = await gphotos_service.auto_populate_journal_photos(
            trip_id=trip_id,
            user_id=current_user['uid'],
            access_token=access_token
        )
        
        return {
            "success": True,
            "message": "Photos automatically populated in journal entries!",
            "result": result
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to auto-populate photos: {str(e)}")

@router.post("/sync-completed-trip/{trip_id}")
async def sync_completed_trip_photos(
    trip_id: str,
    access_token: str,
    current_user: UserInfo = Depends(get_current_user)
):
    """
    🎯 Sync photos when user marks trip as completed.
    This automatically creates journal entries with all photos from the trip.
    """
    try:
        result = await gphotos_service.sync_photos_for_completed_trip(
            trip_id=trip_id,
            user_id=current_user['uid'],
            access_token=access_token
        )
        
        return {
            "success": True,
            "message": "Trip photos synced successfully!",
            "result": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync trip photos: {str(e)}")

@router.get("/trip-summary/{trip_id}")
async def get_trip_photo_summary(
    trip_id: str,
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Get a summary of photos associated with a trip.
    Shows total photos, sample images, and photo organization.
    """
    try:
        summary = gphotos_service.get_trip_photo_summary(
            trip_id=trip_id,
            user_id=current_user['uid']
        )
        
        return {
            "success": True,
            "photo_summary": summary
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get photo summary: {str(e)}")

@router.post("/manual-sync/{trip_id}")
async def manual_photo_sync(
    trip_id: str,
    access_token: str,
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Manual photo sync for when user wants to update photos for an existing trip.
    Useful if user takes more photos and wants to add them to the journal.
    """
    try:
        # First get fresh photos
        scan_result = await gphotos_service.search_photos_by_trip(
            access_token=access_token,
            trip_id=trip_id,
            user_id=current_user['uid']
        )
        
        # Then auto-populate journal
        populate_result = await gphotos_service.auto_populate_journal_photos(
            trip_id=trip_id,
            user_id=current_user['uid'],
            access_token=access_token
        )
        
        return {
            "success": True,
            "message": "Manual photo sync completed!",
            "photos_scanned": scan_result.get("photos_found", 0),
            "journal_updates": populate_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to manually sync photos: {str(e)}")

@router.get("/cache/stats")
async def get_photo_cache_stats():
    """
    Get photo cache statistics for monitoring and debugging.
    """
    try:
        # Access cache stats from the service
        cache_size = len(gphotos_service._photo_cache)
        active_locks = len(gphotos_service._photo_cache_locks)
        
        return {
            "photo_cache_size": cache_size,
            "active_locks": active_locks,
            "cache_info": "Photo scanning cache active"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cache stats: {str(e)}")

@router.delete("/cache/clear")
async def clear_photo_cache():
    """
    Clear photo cache for troubleshooting or to force fresh scans.
    """
    try:
        gphotos_service._photo_cache.clear()
        
        return {
            "success": True,
            "message": "Photo cache cleared successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}") 