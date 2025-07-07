from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from schemas.packing_schema import PackingList, ChecklistGenerateRequest, PackingItem
from services import packing_service, trip_service
from core.security import get_current_user
from schemas.user_schema import UserInfo

router = APIRouter(
    prefix="/packing",
    tags=["packing"],
    responses={404: {"description": "Not found"}},
)

@router.post("/generate", response_model=PackingList)
def generate_checklist(
    request: ChecklistGenerateRequest,
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Generates a new packing checklist for a given trip.
    If a list for this trip already exists, it will be overwritten.
    """
    checklist = packing_service.generate_packing_list(request.trip_id, current_user['uid'])
    if not checklist:
        raise HTTPException(status_code=404, detail="Trip not found, cannot generate checklist.")
    return checklist

@router.get("/{trip_id}", response_model=PackingList)
def get_checklist(
    trip_id: str,
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Retrieves the packing checklist for a specific trip.
    """
    # First, verify the user owns the trip associated with the list.
    trip = trip_service.get_trip_by_id(trip_id)
    if not trip or trip.get('user_id') != current_user['uid']:
        raise HTTPException(status_code=403, detail="You are not authorized to view this packing list.")

    checklist = packing_service.get_packing_list(trip_id)
    if not checklist:
        raise HTTPException(status_code=404, detail="Packing list not found for this trip.")

    return checklist

@router.put("/item/toggle/{trip_id}/{item_id}", response_model=PackingItem)
def toggle_item(
    trip_id: str,
    item_id: str,
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Toggles the 'packed' status of a single checklist item.
    """
    # Authorize: Check if user owns the trip associated with the packing list
    trip = trip_service.get_trip_by_id(trip_id)
    if not trip or trip.get('user_id') != current_user['uid']:
         raise HTTPException(status_code=403, detail="You are not authorized to modify this packing list.")

    updated_item = packing_service.toggle_packed_status(trip_id, item_id)
    if not updated_item:
        raise HTTPException(status_code=404, detail="Packing list item not found.")

    return updated_item 