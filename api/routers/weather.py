from fastapi import APIRouter, Depends, HTTPException, Path

# Import schemas, services, and security dependencies
from schemas.weather_schema import WeatherInfo
from services.weather_service import get_weather_for_location
from core.security import get_current_user

router = APIRouter(
    prefix="/weather",
    tags=["Weather"],
    responses={404: {"description": "Not found"}},
)

@router.get("/{lat}/{lng}", response_model=WeatherInfo)
async def get_weather(
    lat: float = Path(..., description="Latitude of the location"),
    lng: float = Path(..., description="Longitude of the location"),
    current_user: dict = Depends(get_current_user) # Protect the endpoint
):
    """
    Fetches the current weather for a given latitude and longitude.
    """
    try:
        weather_data = await get_weather_for_location(lat=lat, lng=lng)
        return weather_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}") 