from fastapi import APIRouter, Depends, HTTPException
from typing import List
from schemas.journal_schema import JournalEntry, JournalEntryCreate
from core.security import get_current_user
from services import journal_service
from schemas.user_schema import UserInfo

router = APIRouter(
    prefix="/journal",
    tags=["Journal"],
    responses={404: {"description": "Not found"}},
)

@router.post("/entry", response_model=JournalEntry)
async def create_entry(
    entry: JournalEntryCreate,
    current_user: UserInfo = Depends(get_current_user)
):
    """Adds a new journal entry, associated with a trip."""
    try:
        new_entry = journal_service.create_journal_entry(entry_data=entry, user_id=current_user['uid'])
        return new_entry
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/{trip_id}", response_model=List[JournalEntry])
async def get_entries_for_trip(
    trip_id: str,
    current_user: UserInfo = Depends(get_current_user)
):
    """Gets all journal entries for a specific trip."""
    try:
        entries = journal_service.get_journal_entries_by_trip(trip_id=trip_id, user_id=current_user['uid'])
        return entries
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}") 