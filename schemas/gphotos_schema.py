from pydantic import BaseModel, Field
from typing import List

class GPhotosScanRequest(BaseModel):
    """Schema for requesting a smart scan of Google Photos."""
    trip_id: str = Field(..., example="-OTVlf-luH-4fDZGx2ll")
    access_token: str = Field(..., example="ya29.a0AfB... (user's access token)")

class GPhotoItem(BaseModel):
    """Schema representing a single photo item returned from the scan."""
    id: str
    baseUrl: str # The most important field - the URL to display the image
    mediaMetadata: dict
    filename: str

class GPhotosScanResponse(BaseModel):
    """Schema for the response of a smart scan."""
    photos_found: int
    photo_items: List[GPhotoItem] 