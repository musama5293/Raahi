from fastapi import APIRouter, Depends, HTTPException
from typing import List

# Import schemas, services, and security dependencies
from schemas.wishlist_schema import WishlistItemCreate, WishlistItemInfo
from core.security import get_current_user
from services.wishlist_service import add_item_to_wishlist, get_wishlist_for_user

router = APIRouter(
    prefix="/wishlist",
    tags=["Wishlist"],
    responses={404: {"description": "Not found"}},
)

@router.post("/add", response_model=WishlistItemInfo)
async def add_to_wishlist(
    item: WishlistItemCreate,
    current_user: dict = Depends(get_current_user)
):
    """Adds a new destination to the user's wishlist."""
    try:
        user_id = current_user['uid']
        new_item = add_item_to_wishlist(item_data=item, user_id=user_id)
        return new_item
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("", response_model=List[WishlistItemInfo])
async def get_wishlist(current_user: dict = Depends(get_current_user)):
    """Retrieves the full wishlist for the authenticated user."""
    try:
        user_id = current_user['uid']
        wishlist_items = get_wishlist_for_user(user_id=user_id)
        return wishlist_items
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}") 