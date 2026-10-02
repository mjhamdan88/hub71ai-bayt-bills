from django.utils import timezone
from unicom.models import DraftMessage
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

def process_scheduled_messages():
    """
    Processes and sends scheduled messages that are due and approved.
    Returns a summary of operations (e.g., number sent, number failed, total due).
    """
    now = timezone.now()
    
    # Query for messages that are scheduled, approved, past their send_at time, and not yet sent
    scheduled_messages = DraftMessage.objects.filter(
        status='scheduled',
        is_approved=True,
        send_at__lte=now,
        sent_at__isnull=True 
    )
    
    sent_count = 0
    failed_count = 0
    total_due_this_cycle = scheduled_messages.count()

    if not scheduled_messages.exists():
        # No need to log if no messages are due, to keep logs cleaner for a frequently running task.
        # logger.info("No scheduled messages to send at this time.")
        return {"sent": sent_count, "failed": failed_count, "total_due": total_due_this_cycle}

    logger.info(f"Found {total_due_this_cycle} scheduled messages to process.")

    for draft in scheduled_messages:
        try:
            # Use a transaction for each message to ensure atomicity of the send operation and status update
            with transaction.atomic():
                logger.info(f"Attempting to send scheduled message ID: {draft.id} (Channel: {draft.channel.name}, Subject/Text: {draft.subject or draft.text[:30]}...)")
                
                # The draft.send() method is responsible for:
                # 1. Sending the message via the channel.
                # 2. Updating draft.status to 'sent' or 'failed'.
                # 3. Setting draft.sent_at if successful.
                # 4. Setting draft.error_message if failed.
                # 5. Saving the draft object.
                message_instance = draft.send() 
                
                # Check the status after calling send() as it might have failed internally
                if draft.status == 'sent':
                    logger.info(
                        f'Successfully sent scheduled message ID: {draft.id}. Associated message ID: {message_instance.id if message_instance else "N/A"}'
                    )
                    sent_count += 1
                else: # status would be 'failed' if draft.send() had an issue but didn't raise an unhandled exception
                    logger.error(f"Sending scheduled message ID: {draft.id} resulted in status '{draft.status}'. Error: {draft.error_message}")
                    failed_count += 1
                    
        except Exception as e:
            # This catches exceptions from draft.send() if it doesn't handle them and update status itself,
            # or other unexpected errors during processing this specific draft.
            # The draft.send() method should ideally handle its own errors and update status.
            logger.error(f'Critical error processing scheduled message ID: {draft.id}: {str(e)}', exc_info=True)
            failed_count += 1
            # Ensure the draft is marked as failed if an unexpected exception occurred outside draft.send()'s own error handling
            if draft.status != 'failed':
                draft.status = 'failed'
                draft.error_message = f"Scheduler critical error: {str(e)}"
                draft.save(update_fields=['status', 'error_message', 'updated_at'])
            
    return {"sent": sent_count, "failed": failed_count, "total_due": total_due_this_cycle} 