from pydantic import BaseModel, Field
from typing import List, Optional
import datetime

class JournalEntryBase(BaseModel):
    """Base schema for a journal entry, containing common fields."""
    trip_id: str = Field(..., example="-OTVkKdynx9XAowsMP0S")
    title: str = Field(..., example="Day 1: Arrival in Hunza")
    entry_text: str = Field(..., example="The journey was long but the views are incredible.")
    photo_urls: Optional[List[str]] = Field(None, example=["https://photos.google.com/abc", "https://photos.google.com/def"])

class JournalEntryCreate(JournalEntryBase):
    """Schema for creating a new journal entry."""
    pass

class JournalEntry(JournalEntryBase):
    """Schema for returning a journal entry from the database."""
    id: str
    user_id: str
    created_at: str = Field(..., example=str(datetime.datetime.utcnow()))

    class Config:
        from_attributes = True 