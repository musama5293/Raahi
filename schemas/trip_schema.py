from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class Location(BaseModel):
    """Schema for a geographic location."""
    name: str
    lat: float
    lng: float

class TripCreate(BaseModel):
    """Schema for creating a new trip."""
    title: str = Field(..., example="Adventure in Hunza")
    duration_days: int = Field(..., gt=0, example=7)
    start_location: Location
    destinations: List[Location]
    vehicle_type: str = Field(..., example="bike") # "bike" or "car"
    start_date: str = Field(..., example="2024-08-10")
    preferences: Optional[List[str]] = Field(None, example=["nature", "mountains"])

class RouteCalculationRequest(BaseModel):
    """Schema for requesting a route calculation."""
    start_location: Location
    end_location: Location
    vehicle_type: str = Field(..., example="bike")
    route_preference: Optional[str] = Field("fastest", example="scenic")

class Waypoint(BaseModel):
    """Schema for a single point in a calculated route."""
    name: str
    lat: float
    lng: float
    description: Optional[str] = None
    day: Optional[int] = None
    stay_hours: Optional[int] = None

class RouteInfo(BaseModel):
    """Schema for the calculated trip route."""
    total_distance_km: float
    estimated_time_hours: float
    waypoints: Optional[List[Waypoint]] = None
    geometry: Optional[List[List[float]]] = None  # The list of [lng, lat] coordinates for the route line
    description: Optional[str] = None

class SuggestedStop(BaseModel):
    """Schema for a suggested point of interest along a route."""
    name: str
    lat: float
    lng: float
    category: Optional[str] = None
    description: Optional[str] = None
    estimated_visit_time_hours: Optional[float] = None
    tags: Optional[Dict[str, str]] = None

class EnrichedRouteResponse(BaseModel):
    """Schema for returning a route with suggested stops."""
    route_info: RouteInfo
    suggested_stops: List[SuggestedStop]

class LLMRouteResponse(BaseModel):
    """Schema for returning an LLM-generated route with stops."""
    route_id: int = 0
    route_type: str = "LLM Generated Route"
    total_distance_km: float
    estimated_time_hours: float
    description: Optional[str] = None
    waypoints: List[Dict]
    suggested_stops: List[Dict]

class TripInfo(BaseModel):
    """Schema for returning trip information."""
    id: str
    user_id: str
    title: str
    duration_days: int
    vehicle_type: str
    route: Optional[RouteInfo] = None
    created_at: str

class DayPlan(BaseModel):
    """A plan for a single day in a suggested trip."""
    day: int
    title: str
    activities: str

class ComprehensiveTripRequest(BaseModel):
    """Schema for requesting a new comprehensive trip plan."""
    start_location: str = Field(..., example="Islamabad")
    destination: str = Field(..., example="Hunza Valley")
    duration_days: int = Field(..., gt=0, example=7)
    travelers: int = Field(1, gt=0, example=2)
    trip_style: str = Field(..., example="adventure and hiking") # e.g., "relaxing", "historical", "family fun"
    vehicle_type: str = Field("car", example="car") # "car" or "bike"

class ComprehensiveTripPlan(BaseModel):
    """Schema for the AI's suggested comprehensive trip plan."""
    trip_title: str
    summary: str
    route: List[str]
    stop_points: List[str]
    day_by_day_plan: List[DayPlan]
    packing_list: List[str]
    estimated_cost: str 