from django.db.models import Q
from django.db import transaction

def update_chat_summary(message):
    """
    Updates the chat summary fields based on a new message.
    This function is optimized to minimize database queries by:
    1. Only updating fields that are null
    2. Using the new message to update last_* fields directly
    3. Only querying for first_* fields when they are null
    
    Additionally:
    - Automatically unarchives the chat if it receives a new message while archived
    """
    chat = message.chat
    
    with transaction.atomic():
        # Lock the chat for update to prevent race conditions
        chat = type(chat).objects.select_for_update().get(pk=chat.pk)
        
        # Auto-unarchive if needed
        if chat.is_archived:
            chat.is_archived = False
        
        # Update last message fields unconditionally since this is a new message
        chat.last_message = message
        if message.is_outgoing:
            chat.last_outgoing_message = message
        elif message.is_outgoing is False:  # Explicitly check False to handle None case
            chat.last_incoming_message = message
            
        # Update first message fields only if they are null
        if chat.first_message is None:
            chat.first_message = message
            
        if message.is_outgoing and chat.first_outgoing_message is None:
            chat.first_outgoing_message = message
            
        if message.is_outgoing is False and chat.first_incoming_message is None:
            chat.first_incoming_message = message
            
        chat.save() 