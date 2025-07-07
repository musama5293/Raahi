import uuid
from .firebase_service import db
from services.trip_service import get_trip_by_id

def generate_packing_list(trip_id: str, user_id: str):
    """
    Generates a packing list based on trip details.
    For the MVP, this uses a simple rule-based approach.
    """
    trip_data = get_trip_by_id(trip_id)

    if not trip_data or trip_data.get("user_id") != user_id:
        return None # Trip not found or user does not have access

    vehicle_type = trip_data.get("vehicle_type", "car").lower()

    # --- Predefined Packing Items ---
    # category: [item_name, item_name, ...]
    item_templates = {
        "Essentials": [
            "Phone & Charger",
            "Power Bank",
            "Wallet (ID, Cash, Cards)",
            "First-Aid Kit",
            "Medications",
            "Water Bottle",
            "Snacks"
        ],
        "Clothing": [
            "Weather-appropriate Jacket",
            "Sweater / Fleece",
            "T-shirts",
            "Trousers / Jeans",
            "Socks & Underwear",
            "Pajamas",
            "Hiking Shoes / Comfortable Footwear"
        ],
        "Toiletries": [
            "Toothbrush & Toothpaste",
            "Soap / Hand Sanitizer",
            "Sunscreen",
            "Moisturizer",
            "Towel"
        ],
        "Documents": [
            "Driver's License",
            "Vehicle Registration",
            "CNIC / ID Card",
            "Hotel Bookings"
        ],
        "Car Specific": [
            "Spare Tire & Jack",
            "Jumper Cables",
            "Car's Manual",
            "Tire Pressure Gauge"
        ],
        "Bike Specific": [
            "Helmet",
            "Riding Gloves",
            "Puncture Repair Kit",
            "Portable Air Pump",
            "Bike Lock"
        ],
        "Optional": [
            "Camera",
            "Sunglasses",
            "Cap / Hat",
            "Book / Kindle"
        ]
    }

    # --- Logic to Build the List ---
    final_list = []
    # Add base items
    for category in ["Essentials", "Clothing", "Toiletries", "Documents", "Optional"]:
        for item_name in item_templates[category]:
            final_list.append({
                "id": str(uuid.uuid4()),
                "item_name": item_name,
                "category": category,
                "packed": False
            })

    # Add vehicle-specific items
    if vehicle_type == "car":
        for item_name in item_templates["Car Specific"]:
            final_list.append({ "id": str(uuid.uuid4()), "item_name": item_name, "category": "Vehicle", "packed": False })
    elif vehicle_type == "bike":
        for item_name in item_templates["Bike Specific"]:
             final_list.append({ "id": str(uuid.uuid4()), "item_name": item_name, "category": "Vehicle", "packed": False })


    # --- Save to Firebase ---
    # The list is stored in a dictionary keyed by the item's unique ID for easier updates
    list_to_save = {item['id']: item for item in final_list}
    checklist_ref = db.reference(f'packing_lists/{trip_id}')
    checklist_ref.set(list_to_save)

    return {"trip_id": trip_id, "items": final_list}

def get_packing_list(trip_id: str):
    """
    Retrieves a packing list for a given trip_id.
    """
    checklist_ref = db.reference(f'packing_lists/{trip_id}')
    list_data = checklist_ref.get()

    if not list_data:
        return None

    # Convert the dictionary of items back to a list
    items_list = [item for item in list_data.values()]
    return {"trip_id": trip_id, "items": items_list}

def toggle_packed_status(trip_id: str, item_id: str):
    """
    Toggles the 'packed' status of a specific packing list item.
    """
    item_ref = db.reference(f'packing_lists/{trip_id}/{item_id}')
    item_data = item_ref.get()

    if not item_data:
        return None # Item not found

    current_status = item_data.get('packed', False)
    item_ref.update({'packed': not current_status})

    # Return the updated item data
    updated_item = item_ref.get()
    return updated_item 