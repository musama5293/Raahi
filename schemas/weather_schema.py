from pydantic import BaseModel, Field
from typing import Optional

class WeatherInfo(BaseModel):
    """Schema for returning weather information."""
    location: Optional[str] = Field(None, example="Naran")
    temperature_celsius: float = Field(..., example=15.5)
    condition: str = Field(..., example="clear sky")
    humidity_percent: float = Field(..., example=60)
    wind_speed_kph: float = Field(..., example=10.5) 