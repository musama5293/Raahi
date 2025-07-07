from firebase_admin import db
import datetime
from schemas.wishlist_schema import WishlistItemCreate

def add_item_to_wishlist(item_data: WishlistItemCreate, user_id: str):
    """Saves a new item to the user's wishlist in Firebase."""
    try:
        wishlist_ref = db.reference('wishlist')
        new_item_ref = wishlist_ref.push()

        data_to_save = item_data.dict()
        data_to_save['user_id'] = user_id
        data_to_save['created_at'] = datetime.datetime.utcnow().isoformat()
        data_to_save['visited'] = False # Default value

        new_item_ref.set(data_to_save)

        item_id = new_item_ref.key
        
        response_data = data_to_save
        response_data['id'] = item_id

        return response_data
    except Exception as e:
        raise e

def get_wishlist_for_user(user_id: str):
    """Retrieves all wishlist items for a specific user."""
    try:
        wishlist_ref = db.reference('wishlist')
        user_wishlist = wishlist_ref.order_by_child('user_id').equal_to(user_id).get()

        if not user_wishlist:
            return []

        items_list = []
        for item_id, item_data in user_wishlist.items():
            item_data['id'] = item_id
            items_list.append(item_data)
        
        return items_list
    except Exception as e:
        raise e 