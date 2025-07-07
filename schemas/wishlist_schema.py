from pydantic import BaseModel, Field
from typing import Optional

class WishlistItemCreate(BaseModel):
    """Schema for adding an item to the wishlist."""
    place_name: str = Field(..., example="Fairy Meadows")
    lat: float
    lng: float
    category: str = Field(..., example="nature")
    priority: str = Field("medium", example="high") # high, medium, low

class WishlistItemInfo(BaseModel):
    """Schema for returning wishlist item information."""
    id: str
    user_id: str
    place_name: str
    lat: float
    lng: float
    category: str
    priority: str
    visited: bool = False
    created_at: str 