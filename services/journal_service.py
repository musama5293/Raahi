from firebase_admin import db
import datetime
from schemas.journal_schema import JournalEntryCreate, JournalEntry

def create_journal_entry(entry_data: JournalEntryCreate, user_id: str):
    """Saves a new journal entry to the database."""
    # First, verify the trip exists and belongs to the user
    trip_ref = db.reference(f'trips/{user_id}/{entry_data.trip_id}')
    if not trip_ref.get(shallow=True):
        raise ValueError("Trip not found or access denied.")

    # Entries are stored in a top-level collection, indexed by trip_id
    journal_ref = db.reference(f'journal_entries')
    new_entry_ref = journal_ref.push()
    entry_id = new_entry_ref.key

    data_to_save = {
        "id": entry_id,
        "user_id": user_id,
        "trip_id": entry_data.trip_id,
        "title": entry_data.title,
        "entry_text": entry_data.entry_text,
        "photo_urls": entry_data.photo_urls or [],
        "created_at": datetime.datetime.utcnow().isoformat()
    }

    new_entry_ref.set(data_to_save)
    return JournalEntry(**data_to_save)


def get_journal_entries_by_trip(trip_id: str, user_id: str):
    """Retrieves all journal entries for a specific trip."""
    # Verify trip ownership first
    trip_ref = db.reference(f'trips/{user_id}/{trip_id}')
    if not trip_ref.get(shallow=True):
        raise ValueError("Trip not found or access denied.")

    # Query the top-level collection for entries matching the trip_id
    journal_ref = db.reference('journal_entries')
    entries = journal_ref.order_by_child('trip_id').equal_to(trip_id).get()

    if not entries:
        return []

    # As the query is on a user-specific trip, we can assume user has access.
    # The result from the query is a dictionary, we need to convert it to a list.
    return [JournalEntry(**entry_data) for entry_data in entries.values()] 