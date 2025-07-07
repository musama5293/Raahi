from pydantic import BaseModel, Field
from typing import List, Optional

class HotspotGenerateRequest(BaseModel):
    """Schema for requesting a new daily hotspot generation."""
    place_name: str = Field(..., example="Lake Saif-ul-Malook")
    region: str = Field(..., example="Kaghan Valley")

class HotspotInfo(BaseModel):
    """Schema for returning daily hotspot information."""
    id: str
    date: str
    place_name: str
    region: str
    story: str
    highlights: List[str]
    best_time_to_visit: str
    travel_tips: str

class BlogGenerateRequest(BaseModel):
    """Schema for requesting an AI-generated travel blog."""
    trip_id: str = Field(..., example="-OTVkKdynx9XAowsMP0S")
    tone: str = Field("casual", example="storytelling") # casual, guidebook, storytelling

class BlogInfo(BaseModel):
    """Schema for returning a generated blog."""
    id: str
    trip_id: str
    user_id: str
    title: str
    content: str
    tone: str
    created_at: str

class TripSuggestionRequest(BaseModel):
    """Schema for requesting a trip suggestion from the AI."""
    duration_days: int = Field(..., gt=0, example=5)
    vehicle_type: str = Field(..., example="car") # "car" or "bike"
    trip_style: str = Field(..., example="adventure and hiking") # e.g., "relaxing", "historical", "family fun"

class DayPlan(BaseModel):
    """A plan for a single day in a suggested trip."""
    day: int
    title: str
    activities: str

class TripSuggestionResponse(BaseModel):
    """Schema for the AI's suggested trip plan."""
    trip_title: str
    suggested_destination: str
    summary: str
    day_by_day_plan: List[DayPlan]

class ComprehensiveTripRequest(BaseModel):
    """Schema for requesting a new comprehensive trip plan."""
    start_location: str = Field(..., example="Islamabad")
    destination: str = Field(..., example="Hunza Valley")
    duration_days: int = Field(..., gt=0, example=7)
    travelers: int = Field(1, gt=0, example=2)
    trip_style: str = Field(..., example="adventure and hiking")
    vehicle_type: str = Field("car", example="car")

class ComprehensiveTripPlan(BaseModel):
    """Schema for the AI's suggested comprehensive trip plan."""
    trip_title: str
    summary: str
    route: List[str]
    stop_points: List[str]
    day_by_day_plan: List[DayPlan]
    packing_list: List[str]
    estimated_cost: str 