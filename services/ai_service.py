import httpx
from core.config import settings
from firebase_admin import db
import datetime
import json
import random
import asyncio
import hashlib
from typing import Optional, Dict, List

from services.trip_service import get_trip_by_id
from services.journal_service import get_journal_entries_by_trip
from schemas.ai_schema import TripSuggestionRequest, TripSuggestionResponse, ComprehensiveTripRequest, ComprehensiveTripPlan, DayPlan

# In-memory cache for daily hotspot pools
_daily_hotspot_pool_cache: Dict[str, List[dict]] = {}
_cache_timestamps: Dict[str, datetime.datetime] = {}
_generation_locks: Dict[str, asyncio.Lock] = {}
CACHE_DURATION_MINUTES = 60  # Cache for 1 hour
HOTSPOTS_PER_DAY = 4  # Generate 4 different hotspots per day

def _get_cache_key(date_str: str) -> str:
    """Generate cache key for daily hotspot pool"""
    return f"hotspot_pool_{date_str}"

def _is_cache_valid(cache_key: str) -> bool:
    """Check if cached data is still valid"""
    if cache_key not in _cache_timestamps:
        return False
    
    cache_time = _cache_timestamps[cache_key]
    now = datetime.datetime.utcnow()
    duration = now - cache_time
    
    return duration.total_seconds() < (CACHE_DURATION_MINUTES * 60)

def _set_cache(cache_key: str, data: List[dict]):
    """Store data in cache with timestamp"""
    _daily_hotspot_pool_cache[cache_key] = data
    _cache_timestamps[cache_key] = datetime.datetime.utcnow()

def _get_cache(cache_key: str) -> Optional[List[dict]]:
    """Get data from cache if valid"""
    if _is_cache_valid(cache_key):
        return _daily_hotspot_pool_cache.get(cache_key)
    
    # Remove expired cache
    if cache_key in _daily_hotspot_pool_cache:
        del _daily_hotspot_pool_cache[cache_key]
    if cache_key in _cache_timestamps:
        del _cache_timestamps[cache_key]
    
    return None

async def _get_generation_lock(date_str: str) -> asyncio.Lock:
    """Get or create a lock for hotspot generation for a specific date"""
    if date_str not in _generation_locks:
        _generation_locks[date_str] = asyncio.Lock()
    return _generation_locks[date_str]

def _get_user_hotspot_index(user_id: str, date_str: str, pool_size: int) -> int:
    """
    Deterministically assign a user to a hotspot index based on their ID and date.
    This ensures:
    1. Same user gets same hotspot on same day
    2. Different users get different hotspots on same day  
    3. Users get variety across different days
    """
    # Create a hash from user_id + date for deterministic assignment
    hash_input = f"{user_id}_{date_str}".encode('utf-8')
    hash_digest = hashlib.md5(hash_input).hexdigest()
    
    # Convert first 8 characters of hash to integer
    hash_int = int(hash_digest[:8], 16)
    
    # Use modulo to get index within pool size
    return hash_int % pool_size

async def generate_text_with_together_ai(prompt: str, model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo", max_tokens: int = 1024):
    """
    Generic function to generate text using the Together AI API.
    """
    api_key = settings.TOGETHER_API_KEY
    if not api_key:
        raise ValueError("Together AI API key is not configured.")

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }

    async with httpx.AsyncClient() as client:
        try:
            print(f"Sending request to Together AI with model: {model}")
            response = await client.post("https://api.together.xyz/v1/chat/completions", json=body, headers=headers, timeout=60.0)
            
            # Print response status for debugging
            print(f"Together AI response status: {response.status_code}")
            
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                print(f"HTTP error from Together AI: {e.response.status_code}")
                print(f"Response content: {e.response.text[:500]}...")  # Print first 500 chars
                raise Exception(f"Error from Together AI: {e.response.status_code} - {e.response.text[:200]}")
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                print(f"Failed to parse Together AI response as JSON: {e}")
                print(f"Raw response: {response.text[:500]}...")  # Print first 500 chars
                raise Exception(f"Together AI returned invalid JSON response: {e}")
            
            if not data.get('choices') or len(data['choices']) == 0 or not data['choices'][0].get('message'):
                print(f"Unexpected response structure from Together AI: {data}")
                raise Exception("Together AI returned an unexpected response structure")
            
            return data['choices'][0]['message']['content']
        except httpx.HTTPStatusError as e:
            raise Exception(f"Error from Together AI: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            print(f"Request error to Together AI: {e}")
            raise Exception(f"Failed to connect to Together AI: {e}")
        except Exception as e:
            print(f"Unexpected error in generate_text_with_together_ai: {type(e).__name__} - {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"An unexpected error occurred during AI generation: {e}")

async def get_pakistani_destinations():
    """
    Returns a curated list of amazing Pakistani destinations that can be featured as daily hotspots.
    These rotate to ensure users get variety.
    """
    destinations = [
        # Northern Pakistan - Mountains & Lakes
        {"place": "Lake Saif-ul-Malook", "region": "Kaghan Valley"},
        {"place": "Fairy Meadows", "region": "Nanga Parbat"},
        {"place": "Hunza Valley", "region": "Gilgit-Baltistan"},
        {"place": "Skardu", "region": "Baltistan"},
        {"place": "Attabad Lake", "region": "Hunza"},
        {"place": "Ratti Gali Lake", "region": "Azad Kashmir"},
        {"place": "Naran", "region": "Kaghan Valley"},
        {"place": "Shogran", "region": "Kaghan Valley"},
        {"place": "Kumrat Valley", "region": "Upper Dir"},
        {"place": "Chitral", "region": "Khyber Pakhtunkhwa"},
        
        # Western Pakistan - Culture & History
        {"place": "Shandur Polo Ground", "region": "Gilgit-Baltistan"},
        {"place": "Kalash Valley", "region": "Chitral"},
        {"place": "Takht-e-Bahi", "region": "Mardan"},
        {"place": "Peshawar Old City", "region": "Khyber Pakhtunkhwa"},
        
        # Central Pakistan - Hills & Valleys
        {"place": "Murree", "region": "Punjab"},
        {"place": "Patriata (New Murree)", "region": "Punjab"},
        {"place": "Bhurban", "region": "Punjab"},
        {"place": "Nathia Gali", "region": "Galiyat"},
        {"place": "Ayubia", "region": "Galiyat"},
        
        # Southern Pakistan - Deserts & Coast
        {"place": "Hingol National Park", "region": "Balochistan"},
        {"place": "Gwadar Beach", "region": "Balochistan"},
        {"place": "Thar Desert", "region": "Sindh"},
        {"place": "Keenjhar Lake", "region": "Sindh"},
        
        # Hidden Gems
        {"place": "Deosai Plains", "region": "Gilgit-Baltistan"},
        {"place": "Khunjerab Pass", "region": "Gilgit-Baltistan"},
        {"place": "Manthoka Waterfall", "region": "Skardu"},
        {"place": "Kachura Lakes", "region": "Skardu"},
        {"place": "Naltar Valley", "region": "Gilgit-Baltistan"},
        {"place": "Ushu Forest", "region": "Kaghan Valley"},
        
        # Adventure Spots
        {"place": "K2 Base Camp", "region": "Baltistan"},
        {"place": "Concordia", "region": "Baltistan"},
        {"place": "Rakaposhi Base Camp", "region": "Nagar"},
        {"place": "Trango Towers", "region": "Baltistan"},
        
        # Cultural Sites
        {"place": "Badshahi Mosque", "region": "Lahore"},
        {"place": "Lahore Fort", "region": "Lahore"},
        {"place": "Mohatta Palace", "region": "Karachi"},
        {"place": "Quaid-e-Azam Residency", "region": "Ziarat"},
        
        # Seasonal Favorites
        {"place": "Swat Valley", "region": "Khyber Pakhtunkhwa"},
        {"place": "Kalam", "region": "Swat"},
        {"place": "Malam Jabba", "region": "Swat"},
        {"place": "Ushu Valley", "region": "Swat"},
    ]
    return destinations

async def get_daily_destinations_pool():
    """
    Returns multiple curated Pakistani destinations for a single day.
    These are selected to provide variety within the same day.
    """
    all_destinations = await get_pakistani_destinations()
    
    # Use date to seed random selection for consistent daily pools
    today = datetime.date.today()
    day_of_year = today.timetuple().tm_yday
    
    # Create a deterministic seed based on the date
    random.seed(day_of_year + today.year)
    
    # Select HOTSPOTS_PER_DAY destinations randomly but deterministically
    daily_pool = random.sample(all_destinations, min(HOTSPOTS_PER_DAY, len(all_destinations)))
    
    # Reset random seed to avoid affecting other random operations
    random.seed()
    
    return daily_pool

async def generate_daily_hotspot_pool():
    """
    Generates a pool of hotspots for today (typically 4 different destinations).
    This pool is shared among all users but each user sees a different one.
    """
    today_str = datetime.date.today().isoformat()
    destinations_pool = await get_daily_destinations_pool()
    
    print(f"🎯 Generating {len(destinations_pool)} hotspots for {today_str}")
    
    hotspot_pool = []
    
    for i, destination in enumerate(destinations_pool):
        try:
            print(f"   Generating hotspot {i+1}/{len(destinations_pool)}: {destination['place']}")
            
            hotspot_data = await generate_and_save_daily_hotspot_content(
                place_name=destination["place"],
                region=destination["region"],
                pool_index=i
            )
            
            hotspot_pool.append(hotspot_data)
            
        except Exception as e:
            print(f"   ❌ Failed to generate hotspot {i+1}: {e}")
            # Continue with other hotspots even if one fails
    
    if not hotspot_pool:
        raise Exception("Failed to generate any hotspots for today")
    
    # Save the entire pool to Firebase
    try:
        pool_ref = db.reference(f'hotspot_pools/{today_str}')
        pool_ref.set({
            "date": today_str,
            "hotspots": hotspot_pool,
            "generated_at": datetime.datetime.utcnow().isoformat()
        })
        print(f"✅ Saved hotspot pool with {len(hotspot_pool)} hotspots to Firebase")
    except Exception as e:
        print(f"⚠️ Failed to save hotspot pool to Firebase: {e}")
    
    return hotspot_pool

async def get_or_generate_daily_hotspot_pool():
    """
    Gets today's hotspot pool if it exists, or generates a new one.
    Returns a list of hotspots for the day.
    """
    today_str = datetime.date.today().isoformat()
    cache_key = _get_cache_key(today_str)
    
    # Step 1: Check in-memory cache first
    cached_pool = _get_cache(cache_key)
    if cached_pool:
        print(f"📦 Returning hotspot pool from memory cache for {today_str}")
        return cached_pool
    
    # Step 2: Use lock to prevent multiple simultaneous generations
    lock = await _get_generation_lock(today_str)
    
    async with lock:
        # Double-check cache after acquiring lock
        cached_pool = _get_cache(cache_key)
        if cached_pool:
            print(f"📦 Returning hotspot pool from memory cache (post-lock) for {today_str}")
            return cached_pool
        
        print(f"🔍 Checking Firebase for existing hotspot pool: {today_str}")
        
        # Step 3: Check Firebase database
        try:
            pool_ref = db.reference(f'hotspot_pools/{today_str}')
            existing_pool = pool_ref.get()
            
            if existing_pool and existing_pool.get('hotspots'):
                print(f"📥 Found existing hotspot pool in Firebase for {today_str}")
                hotspot_list = existing_pool['hotspots']
                
                # Cache the result for future requests
                _set_cache(cache_key, hotspot_list)
                return hotspot_list
            
        except Exception as e:
            print(f"⚠️ Error checking Firebase for hotspot pool: {e}")
        
        # Step 4: Generate new hotspot pool
        print(f"🤖 Generating new hotspot pool for {today_str}")
        
        try:
            new_pool = await generate_daily_hotspot_pool()
            
            # Cache the newly generated pool
            _set_cache(cache_key, new_pool)
            
            print(f"✅ Generated and cached new hotspot pool for {today_str} with {len(new_pool)} hotspots")
            return new_pool
            
        except Exception as e:
            print(f"❌ Error generating hotspot pool: {e}")
            raise e

async def get_user_daily_hotspot(user_id: str):
    """
    Gets the specific hotspot for a user on today's date.
    Each user gets a different hotspot from the daily pool, but consistently
    gets the same one on the same day.
    """
    # Get today's hotspot pool
    hotspot_pool = await get_or_generate_daily_hotspot_pool()
    
    if not hotspot_pool:
        raise Exception("No hotspots available for today")
    
    # Determine which hotspot this user should see
    today_str = datetime.date.today().isoformat()
    user_index = _get_user_hotspot_index(user_id, today_str, len(hotspot_pool))
    
    user_hotspot = hotspot_pool[user_index]
    
    print(f"👤 User {user_id[:8]}... assigned hotspot {user_index + 1}/{len(hotspot_pool)}: {user_hotspot.get('place_name', 'Unknown')}")
    
    # Add some metadata for the user
    user_hotspot_copy = user_hotspot.copy()
    user_hotspot_copy['id'] = f"{today_str}_{user_id[:8]}_{user_index}"  # Create unique ID for this user's hotspot
    user_hotspot_copy['user_assignment'] = {
        'user_index': user_index + 1,
        'total_hotspots_today': len(hotspot_pool),
        'assigned_at': datetime.datetime.utcnow().isoformat()
    }
    
    return user_hotspot_copy

async def generate_and_save_daily_hotspot_content(place_name: str, region: str, pool_index: int = 0):
    """
    Generates content for a single hotspot (part of daily pool).
    """
    prompt = f"""
    Create an engaging daily feature about "{place_name}" in "{region}, Pakistan".
    Make this sound exciting and inspiring for travelers. Focus on what makes this place special and unique.
    
    Your response MUST be a JSON object with the following exact keys: "story", "highlights", "best_time_to_visit", "travel_tips".
    - "story": Write a captivating 2-3 sentence description that makes people want to visit. Include any interesting history, legends, or unique features. Keep it under 200 words.
    - "highlights": A JSON array of exactly 3 exciting highlights that make this place special.
    - "best_time_to_visit": A short phrase indicating the best season, e.g., "April to October" or "Year-round".
    - "travel_tips": A practical paragraph with helpful advice for visitors (transportation, accommodation, what to bring, etc.).

    Example JSON response format:
    {{
        "story": "Nestled in the heart of the Karakoram range, this breathtaking destination offers views that will leave you speechless. Legend says that fairies once danced on its shores under the moonlight, giving it an ethereal beauty that captivates every visitor.",
        "highlights": ["Crystal clear emerald waters", "Spectacular mountain reflections", "Perfect for sunrise photography"],
        "best_time_to_visit": "May to September",
        "travel_tips": "The journey requires a 4WD vehicle due to rough terrain. Book accommodation in advance during peak season. Don't forget warm clothing as temperatures drop significantly at night, even in summer."
    }}
    """

    try:
        generated_content = await generate_text_with_together_ai(prompt, max_tokens=1200)
        
        # Extract JSON from AI response
        json_response_str = generated_content[generated_content.find('{'):generated_content.rfind('}')+1]
        ai_data = json.loads(json_response_str)

        today_str = datetime.date.today().isoformat()
        
        hotspot_data = {
            "date": today_str,
            "place_name": place_name,
            "region": region,
            "pool_index": pool_index,
            "story": ai_data.get("story"),
            "highlights": ai_data.get("highlights", []),
            "best_time_to_visit": ai_data.get("best_time_to_visit"),
            "travel_tips": ai_data.get("travel_tips"),
            "generated_at": datetime.datetime.utcnow().isoformat()
        }

        return hotspot_data

    except json.JSONDecodeError as e:
        raise Exception(f"Failed to decode AI response into JSON: {e}")
    except Exception as e:
        raise e

# Keep the old function for backward compatibility but mark it as deprecated
async def generate_and_save_daily_hotspot(place_name: str, region: str):
    """
    DEPRECATED: Use generate_and_save_daily_hotspot_content instead.
    This function is kept for backward compatibility only.
    """
    return await generate_and_save_daily_hotspot_content(place_name, region, 0)

# Update cache management functions
async def get_cached_hotspot_info():
    """
    Returns information about the current cache state (for debugging/monitoring)
    """
    cache_info = {
        "cached_dates": list(_daily_hotspot_pool_cache.keys()),
        "cache_count": len(_daily_hotspot_pool_cache),
        "cache_validity": {}
    }
    
    for date_str in _daily_hotspot_pool_cache.keys():
        cache_key = _get_cache_key(date_str.replace("hotspot_pool_", ""))
        cache_info["cache_validity"][date_str] = _is_cache_valid(cache_key)
    
    return cache_info

async def clear_hotspot_cache(date_str: Optional[str] = None):
    """
    Clear hotspot cache. If date_str is provided, clear only that date.
    If None, clear all cache.
    """
    if date_str:
        cache_key = _get_cache_key(date_str)
        if cache_key in _daily_hotspot_pool_cache:
            del _daily_hotspot_pool_cache[cache_key]
        if cache_key in _cache_timestamps:
            del _cache_timestamps[cache_key]
        print(f"🗑️ Cleared cache for {date_str}")
    else:
        _daily_hotspot_pool_cache.clear()
        _cache_timestamps.clear()
        print("🗑️ Cleared all hotspot cache")

async def force_regenerate_daily_hotspot_pool():
    """
    Forces regeneration of today's hotspot pool, bypassing all caches.
    Useful for admin operations.
    """
    today_str = datetime.date.today().isoformat()
    
    # Clear cache first
    await clear_hotspot_cache(today_str)
    
    # Delete from Firebase to force regeneration
    try:
        pool_ref = db.reference(f'hotspot_pools/{today_str}')
        pool_ref.delete()
        print(f"🗑️ Deleted existing Firebase hotspot pool for {today_str}")
    except Exception as e:
        print(f"⚠️ Could not delete Firebase hotspot pool: {e}")
    
    # Generate new hotspot pool
    print(f"🔄 Force regenerating hotspot pool for {today_str}")
    return await get_or_generate_daily_hotspot_pool()

async def generate_and_save_trip_blog(trip_id: str, user_id: str, tone: str):
    """
    Generates a travel blog for a completed trip using AI and saves it.
    """
    # Step 1: Fetch all necessary data
    trip_data = get_trip_by_id(trip_id=trip_id)
    if not trip_data or trip_data.get('user_id') != user_id:
        raise ValueError("Trip not found or access denied.")

    journal_entries = get_journal_entries_by_trip(trip_id=trip_id, user_id=user_id)
    
    # Step 2: Build a detailed prompt
    journal_summary = "\\n".join(
        [f"- {entry.title}: {entry.entry_text}" for entry in journal_entries]
    )

    prompt = f"""
    Write a high-quality, engaging travel blog post in a "{tone}" tone about a trip to {trip_data['title']}.
    The trip was {trip_data['duration_days']} days long by {trip_data['vehicle_type']}.
    The journey started from {trip_data['start_location']['name']}.

    Use the following journal entries to structure the narrative:
    {journal_summary}

    The blog post should have:
    1. A catchy, creative title.
    2. An introduction that hooks the reader.
    3. A body that flows well, telling the story of the trip based on the journal entries.
    4. A concluding paragraph summarizing the experience.

    Do not just list the journal entries. Weave them into a compelling story.
    The final output should be the full blog post content as a single block of text. Do not include markdown formatting like "###".
    """

    # Step 3: Generate the blog content
    generated_content = await generate_text_with_together_ai(prompt, max_tokens=2048)

    # Step 4: Save the blog to Firebase
    blog_data = {
        "trip_id": trip_id,
        "user_id": user_id,
        "title": trip_data['title'], # We could have the AI generate a title too
        "content": generated_content,
        "tone": tone,
        "created_at": datetime.datetime.utcnow().isoformat()
    }

    blogs_ref = db.reference('blogs')
    new_blog_ref = blogs_ref.push()
    new_blog_ref.set(blog_data)

    blog_id = new_blog_ref.key
    blog_data['id'] = blog_id

    return blog_data

async def generate_trip_suggestion(request: TripSuggestionRequest) -> TripSuggestionResponse:
    """
    Generates a personalized trip suggestion using an AI model.
    """
    prompt = f"""
    Act as an expert travel agent specializing in road trips in Pakistan. A user wants a suggestion for a new trip.

    User's requirements:
    - Duration: {request.duration_days} days
    - Vehicle: {request.vehicle_type}
    - Desired Style: {request.trip_style}

    Based on these requirements, create a single, compelling trip suggestion. Your response MUST be a valid JSON object that conforms to the following structure:
    {{
      "trip_title": "A creative and exciting title for the trip",
      "suggested_destination": "The primary destination area, e.g., 'Skardu Valley' or 'Swat Valley'",
      "summary": "A short, engaging paragraph summarizing the trip and why it fits the user's style.",
      "day_by_day_plan": [
        {{
          "day": 1,
          "title": "A short title for Day 1's plan",
          "activities": "A description of the day's activities, including driving, key stops, and what to do at the destination."
        }},
        {{
          "day": 2,
          "title": "A short title for Day 2's plan",
          "activities": "A description of the day's activities..."
        }}
      ]
    }}

    Ensure the plan is realistic for the given duration and vehicle type. For example, do not suggest a 2-day trip to Hunza from Karachi. The plan should be detailed enough to be useful.
    """
    
    try:
        # We expect the AI to return a JSON object as a string
        generated_content = await generate_text_with_together_ai(prompt, max_tokens=3072)
        
        # Find and parse the JSON part of the response
        json_response_str = generated_content[generated_content.find('{'):generated_content.rfind('}')+1]
        ai_data = json.loads(json_response_str)
        
        # Validate the response with Pydantic
        suggestion = TripSuggestionResponse(**ai_data)
        return suggestion

    except json.JSONDecodeError:
        raise Exception("Failed to decode AI response into JSON. The AI may have returned a malformed response.")
    except Exception as e:
        print(f"Error during trip suggestion generation: {e}")
        raise e 

async def generate_route_with_stops(start_location: str, end_location: str, vehicle_type: str = "car", route_preference: str = "fastest"):
    """
    Generates a route with suggested stops using an external API or AI.
    This is a placeholder and should be replaced with a real implementation.
    """
    print(f"Generating route from {start_location} to {end_location} for a {vehicle_type} ({route_preference}).")
    # In a real implementation, you would call Google Maps API, Mapbox, or an AI model
    # For now, return a dummy route
    return {
        "route": [f"{start_location}", "Mid-way Stop 1", "Mid-way Stop 2", f"{end_location}"],
        "stops": ["Scenic Viewpoint", "Local Restaurant", "Historical Landmark"]
    }

async def generate_comprehensive_trip_plan(request: ComprehensiveTripRequest, user_id: str) -> ComprehensiveTripPlan:
    """
    Generates a comprehensive, AI-powered trip plan based on user requirements.
    """
    print(f"Generating comprehensive trip plan for user {user_id} with request: {request.model_dump_json()}")

    prompt = f"""
    Act as an expert, cautious, and practical travel planner specializing in road trips in Pakistan. Your top priority is creating a safe, realistic, and enjoyable itinerary. You must strictly adhere to the expert context provided below.

    **Expert Knowledge & Constraints (Non-negotiable):**
    - **Mountain Driving is Slow:** Assume an average speed of 30-40 km/h on mountain roads (KKH, Skardu Road, etc.). A 300km journey will take 8-10 hours.
    - **Strict Daily Driving Limit:** Never suggest a single day of driving that exceeds 8 hours in mountainous regions. Prioritize safety over speed.
    - **Break Down Major Routes:**
        - **Islamabad to Hunza (~15 hours driving):** MUST be a 2-day journey.
            - **Route 1 (Summer - June to Oct):** Islamabad -> Naran (overnight) -> Hunza (via Babusar Pass). This is the scenic route.
            - **Route 2 (All-Year):** Islamabad -> Besham or Chilas (overnight) -> Hunza (via KKH). Use this if Babusar is closed.
        - **Islamabad to Skardu (~18 hours driving):** MUST be a 2-day journey. The road is challenging.
            - **Route:** Islamabad -> Chilas (overnight) -> Skardu.
    - **Acclimatization:** For high-altitude areas like Hunza or Skardu (above 3,000m), the plan should include a day of rest or light activity upon arrival to prevent altitude sickness.
    - **Vehicle Suitability:** A '{request.vehicle_type}' has been requested. A bike trip might need shorter daily distances and more frequent stops than a 4x4 car. A standard car might not be suitable for very rough roads (e.g., Deosai Plains). Tailor suggestions accordingly.

    **User's Trip Request:**
    - **Start Location:** {request.start_location}
    - **Destination:** {request.destination}
    - **Duration:** {request.duration_days} days
    - **Travelers:** {request.travelers}
    - **Trip Style:** {request.trip_style}
    - **Vehicle:** {request.vehicle_type}

    **Your Task:**
    Create a complete, safe, and practical travel plan based on the user's request, strictly following the expert knowledge and constraints.

    **JSON Output Schema:**
    Your response MUST be a single, valid JSON object with the following exact structure. Do not add any text before or after the JSON.
    {{
      "trip_title": "A creative, catchy title for the trip.",
      "summary": "A compelling 2-3 sentence summary of the trip, highlighting the key experiences and mentioning the overnight stops.",
      "route": ["A JSON array of strings representing the main overnight locations, e.g., ["Islamabad", "Naran", "Hunza Valley", "Naran", "Islamabad"]],
      "stop_points": ["A JSON array of strings for at least 5 interesting suggested stops along the entire route."],
      "day_by_day_plan": [
        {{
          "day": 1,
          "title": "A short, descriptive title for the day's plan (e.g., 'Journey to the Mountains: Islamabad to Naran').",
          "activities": "A detailed paragraph describing the day's activities, including a realistic driving time estimate (e.g., 'approx. 7-8 hours'), key stops, and suggested meals."
        }}
      ],
      "packing_list": ["A JSON array of at least 5 essential items to pack for this specific trip, including things like 'sunscreen', 'power bank', 'warm layers'."],
      "estimated_cost": "A string describing the estimated cost per person, including a breakdown (e.g., 'Approx. 50,000 - 70,000 PKR per person, covering fuel, mid-range hotels, and food')."
    }}
    """

    try:
        # Use a powerful model for complex generation. Switched to a valid model.
        generated_content = await generate_text_with_together_ai(prompt, model="meta-llama/Llama-3.3-70B-Instruct-Turbo", max_tokens=6000)
        
        # Clean up the response to extract only the JSON
        json_response_str = generated_content[generated_content.find('{'):generated_content.rfind('}')+1]
        
        ai_data = json.loads(json_response_str)
        
        # Validate the response with Pydantic
        plan = ComprehensiveTripPlan(**ai_data)
        return plan

    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        print(f"AI Response was: {generated_content}")
        raise Exception("Failed to decode the AI's response into a valid trip plan.")
    except Exception as e:
        print(f"An error occurred during comprehensive trip plan generation: {e}")
        raise e 