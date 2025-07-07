from pydantic import BaseModel, Field
from typing import List

class PackingItem(BaseModel):
    """Schema for a single item in a packing list."""
    id: str
    item_name: str = Field(..., example="Warm Jacket")
    category: str = Field(..., example="Clothing")
    packed: bool = False

class PackingList(BaseModel):
    """Schema for returning a full packing list."""
    trip_id: str
    items: List[PackingItem]

class ChecklistGenerateRequest(BaseModel):
    """Schema for requesting a new checklist generation."""
    trip_id: str = Field(..., example="-OTVlf-luH-4fDZGx2ll") 