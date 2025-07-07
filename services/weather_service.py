import httpx
from core.config import settings

async def get_weather_for_location(lat: float, lng: float):
    """
    Fetches the current weather for a specific latitude and longitude
    from the OpenWeatherMap API.
    """
    api_key = settings.OPENWEATHER_API_KEY
    if not api_key:
        raise ValueError("OpenWeatherMap API key is not configured.")

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lng,
        "appid": api_key,
        "units": "metric"  # Get temperature in Celsius
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return {
                "location": data.get("name"),
                "temperature_celsius": data["main"].get("temp"),
                "condition": data["weather"][0].get("description"),
                "humidity_percent": data["main"].get("humidity"),
                "wind_speed_kph": data["wind"].get("speed") * 3.6  # Convert m/s to kph
            }
        except httpx.HTTPStatusError as e:
            raise Exception(f"Error from OpenWeatherMap API: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise Exception(f"An unexpected error occurred during weather fetch: {e}") 