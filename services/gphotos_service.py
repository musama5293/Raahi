from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from services.trip_service import get_trip_by_id
from firebase_admin import db
import datetime
import hashlib
import asyncio
from typing import List, Dict, Optional

# Photo caching system
_photo_cache = {}
_photo_cache_locks = {}

def _get_photo_cache_key(user_id: str, trip_id: str) -> str:
    """Generate cache key for photo searches"""
    return hashlib.md5(f"photos:{user_id}:{trip_id}".encode()).hexdigest()

async def search_photos_by_trip(access_token: str, trip_id: str, user_id: str):
    """
    Enhanced photo search with caching and intelligent date range detection.
    Automatically finds photos taken during the trip period.
    """
    # Check cache first
    cache_key = _get_photo_cache_key(user_id, trip_id)
    if cache_key in _photo_cache:
        cache_entry = _photo_cache[cache_key]
        if datetime.datetime.now() < cache_entry['expires_at']:
            print(f"📸 Photo cache HIT: {trip_id}")
            return cache_entry['data']

    # Prevent duplicate searches
    if cache_key in _photo_cache_locks:
        await _photo_cache_locks[cache_key].wait()
        if cache_key in _photo_cache:
            return _photo_cache[cache_key]['data']

    _photo_cache_locks[cache_key] = asyncio.Event()

    try:
        # Step 1: Get trip details
        trip = get_trip_by_id(trip_id)
        if not trip or trip.get("user_id") != user_id:
            raise ValueError("Trip not found or access denied.")

        # Step 2: Calculate intelligent date range
        photo_search_result = await _search_trip_photos(access_token, trip)
        
        # Step 3: Process and enhance photos
        enhanced_photos = await _process_trip_photos(photo_search_result, trip)
        
        # Step 4: Cache results
        result = {
            "trip_id": trip_id,
            "photos_found": len(enhanced_photos),
            "photo_items": enhanced_photos,
            "search_date_range": photo_search_result.get("date_range"),
            "auto_scanned": True,
            "scan_timestamp": datetime.datetime.now().isoformat()
        }
        
        # Cache for 2 hours (photos don't change often during active trips)
        _photo_cache[cache_key] = {
            'data': result,
            'expires_at': datetime.datetime.now() + datetime.timedelta(hours=2)
        }
        
        return result

    finally:
        _photo_cache_locks[cache_key].set()
        del _photo_cache_locks[cache_key]

async def _search_trip_photos(access_token: str, trip: dict) -> dict:
    """
    Search Google Photos with intelligent date range calculation.
    """
    start_date_str = trip.get("start_date")
    duration = trip.get("duration_days", 1)

    if not start_date_str:
        raise ValueError("Trip is missing start date information.")

    # Calculate extended date range (include day before and after for travel time)
    start_date = datetime.date.fromisoformat(start_date_str)
    search_start_date = start_date - datetime.timedelta(days=1)  # Day before trip
    search_end_date = start_date + datetime.timedelta(days=duration + 1)  # Day after trip

    # Format for Google Photos API
    gphotos_start_date = {
        "year": search_start_date.year, 
        "month": search_start_date.month, 
        "day": search_start_date.day
    }
    gphotos_end_date = {
        "year": search_end_date.year, 
        "month": search_end_date.month, 
        "day": search_end_date.day
    }

    # Enhanced search parameters
    search_body = {
        "pageSize": 100,
        "filters": {
            "dateFilter": {
                "ranges": [{
                    "startDate": gphotos_start_date,
                    "endDate": gphotos_end_date
                }]
            },
            "contentFilter": {
                "includedContentCategories": [
                    "LANDSCAPES", "TRAVEL", "PEOPLE", "CITYSCAPES", 
                    "NATURE", "PERFORMANCES", "FOOD", "SPORT"
                ]
            },
            "mediaTypeFilter": {
                "mediaTypes": ["PHOTO"]
            }
        }
    }

    print(f"📸 Searching Google Photos: {trip['title']}")
    print(f"   Date Range: {search_start_date} to {search_end_date}")

    try:
        # Set up Google Photos API client
        creds = Credentials(token=access_token)
        service = build('photoslibrary', 'v1', credentials=creds, static_discovery=False)
        
        # Execute search
        response = service.mediaItems().search(body=search_body).execute()
        items = response.get("mediaItems", [])
        
        print(f"✅ Found {len(items)} photos for trip")
        
        return {
            "photos": items,
            "date_range": {
                "start": search_start_date.isoformat(),
                "end": search_end_date.isoformat()
            },
            "search_params": search_body
        }
        
    except Exception as e:
        print(f"❌ Google Photos API error: {e}")
        raise ValueError(f"Failed to retrieve photos from Google: {str(e)}")

async def _process_trip_photos(search_result: dict, trip: dict) -> List[dict]:
    """
    Process and enhance found photos with trip context.
    """
    photos = search_result.get("photos", [])
    enhanced_photos = []
    
    trip_destinations = trip.get("destinations", [])
    trip_start_location = trip.get("start_location", {})
    
    for photo in photos:
        try:
            enhanced_photo = {
                "id": photo.get("id"),
                "baseUrl": photo.get("baseUrl"),
                "filename": photo.get("filename"),
                "mimeType": photo.get("mimeType"),
                "creationTime": photo.get("mediaMetadata", {}).get("creationTime"),
                "width": photo.get("mediaMetadata", {}).get("width"),
                "height": photo.get("mediaMetadata", {}).get("height"),
                
                # Enhanced fields for trip context
                "trip_context": {
                    "trip_id": trip["id"],
                    "trip_title": trip["title"],
                    "auto_discovered": True,
                    "potential_location": _guess_photo_location(photo, trip_destinations, trip_start_location)
                },
                
                # Quick access URL for display
                "thumbnail_url": f"{photo.get('baseUrl')}=w400-h300-c",
                "display_url": f"{photo.get('baseUrl')}=w800-h600-c"
            }
            
            enhanced_photos.append(enhanced_photo)
            
        except Exception as e:
            print(f"⚠️ Error processing photo {photo.get('id', 'unknown')}: {e}")
            continue
    
    return enhanced_photos

def _guess_photo_location(photo: dict, destinations: List[dict], start_location: dict) -> str:
    """
    Intelligently guess which location a photo was taken at based on timestamp and trip itinerary.
    """
    creation_time = photo.get("mediaMetadata", {}).get("creationTime")
    if not creation_time:
        return "Unknown location"
    
    try:
        # Parse creation time
        photo_time = datetime.datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
        
        # Simple heuristic: if only one destination, assume it's there
        if len(destinations) == 1:
            return destinations[0].get("name", "Trip destination")
        
        # For multiple destinations, could implement more sophisticated logic
        # For now, return the first destination
        if destinations:
            return destinations[0].get("name", "Trip destination")
        
        return start_location.get("name", "Trip location")
        
    except Exception:
        return "Trip location"

async def auto_populate_journal_photos(trip_id: str, user_id: str, access_token: str) -> dict:
    """
    Automatically populate journal entries with photos from Google Photos.
    This is called after trip creation or when user requests photo sync.
    """
    try:
        print(f"🔄 Auto-populating photos for trip: {trip_id}")
        
        # Get photos for the trip
        photo_result = await search_photos_by_trip(access_token, trip_id, user_id)
        photos = photo_result.get("photo_items", [])
        
        if not photos:
            return {
                "status": "no_photos",
                "message": "No photos found for this trip period",
                "photos_found": 0
            }
        
        # Group photos by day for better journal organization
        daily_photos = _group_photos_by_day(photos)
        
        # Create or update journal entries with photos
        journal_updates = await _create_photo_journal_entries(trip_id, user_id, daily_photos)
        
        return {
            "status": "success",
            "photos_found": len(photos),
            "daily_groups": len(daily_photos),
            "journal_entries_created": len(journal_updates),
            "auto_populated": True,
            "photos_by_day": {day: len(photos) for day, photos in daily_photos.items()}
        }
        
    except Exception as e:
        print(f"❌ Auto photo population error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "photos_found": 0
        }

def _group_photos_by_day(photos: List[dict]) -> dict:
    """
    Group photos by the day they were taken.
    """
    daily_groups = {}
    
    for photo in photos:
        try:
            creation_time = photo.get("creationTime")
            if creation_time:
                # Parse and get date
                photo_time = datetime.datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                date_key = photo_time.date().isoformat()
                
                if date_key not in daily_groups:
                    daily_groups[date_key] = []
                daily_groups[date_key].append(photo)
                
        except Exception as e:
            print(f"⚠️ Error grouping photo: {e}")
            continue
    
    return daily_groups

async def _create_photo_journal_entries(trip_id: str, user_id: str, daily_photos: dict) -> List[dict]:
    """
    Create journal entries with auto-discovered photos.
    """
    journal_entries = []
    
    for date_str, photos in daily_photos.items():
        try:
            # Create a journal entry for each day with photos
            entry_data = {
                "trip_id": trip_id,
                "user_id": user_id,
                "date": date_str,
                "title": f"Photos from {date_str}",
                "entry_text": f"Discovered {len(photos)} photos from this day of the trip.",
                "auto_generated": True,
                "created_at": datetime.datetime.now().isoformat(),
                "photos": [
                    {
                        "google_photo_id": photo["id"],
                        "url": photo["display_url"],
                        "thumbnail_url": photo["thumbnail_url"],
                        "filename": photo.get("filename", ""),
                        "location_guess": photo["trip_context"]["potential_location"]
                    }
                    for photo in photos[:10]  # Limit to 10 photos per day
                ]
            }
            
            # Save to Firebase
            journal_ref = db.reference('journal_entries')
            new_entry_ref = journal_ref.push()
            new_entry_ref.set(entry_data)
            
            entry_data['id'] = new_entry_ref.key
            journal_entries.append(entry_data)
            
            print(f"📝 Created journal entry for {date_str} with {len(entry_data['photos'])} photos")
            
        except Exception as e:
            print(f"❌ Error creating journal entry for {date_str}: {e}")
            continue
    
    return journal_entries

async def sync_photos_for_completed_trip(trip_id: str, user_id: str, access_token: str) -> dict:
    """
    Sync photos for a completed trip. Called when user marks trip as complete.
    """
    try:
        print(f"🔄 Syncing photos for completed trip: {trip_id}")
        
        # Auto-populate journal with photos
        result = await auto_populate_journal_photos(trip_id, user_id, access_token)
        
        # Update trip with photo sync status
        trip_ref = db.reference(f'trips/{trip_id}')
        trip_ref.update({
            "photos_synced": True,
            "photos_sync_timestamp": datetime.datetime.now().isoformat(),
            "photos_found": result.get("photos_found", 0)
        })
        
        return result
        
    except Exception as e:
        print(f"❌ Photo sync error: {e}")
        return {"status": "error", "message": str(e)}

def get_trip_photo_summary(trip_id: str, user_id: str) -> dict:
    """
    Get a summary of photos associated with a trip.
    """
    try:
        # Get journal entries with photos for this trip
        journal_ref = db.reference('journal_entries')
        entries = journal_ref.order_by_child('trip_id').equal_to(trip_id).get()
        
        total_photos = 0
        photo_days = 0
        sample_photos = []
        
        if entries:
            for entry_id, entry_data in entries.items():
                if entry_data.get('user_id') == user_id and 'photos' in entry_data:
                    photos = entry_data['photos']
                    total_photos += len(photos)
                    photo_days += 1
                    
                    # Collect sample photos for preview
                    for photo in photos[:3]:  # Max 3 per entry
                        if len(sample_photos) < 6:  # Max 6 total
                            sample_photos.append(photo)
        
        return {
            "trip_id": trip_id,
            "total_photos": total_photos,
            "photo_days": photo_days,
            "sample_photos": sample_photos,
            "has_photos": total_photos > 0
        }
        
    except Exception as e:
        print(f"❌ Error getting photo summary: {e}")
        return {
            "trip_id": trip_id,
            "total_photos": 0,
            "photo_days": 0,
            "sample_photos": [],
            "has_photos": False,
            "error": str(e)
        } 