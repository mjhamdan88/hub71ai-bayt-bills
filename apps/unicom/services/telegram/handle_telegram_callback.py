# unicom.services.telegram.handle_telegram_callback.py
from __future__ import annotations
from typing import TYPE_CHECKING
from django.db import transaction
from unicom.models import CallbackExecution, Message, Account
from unicom.signals import telegram_callback_received
from unicom.services.telegram.answer_callback_query import answer_callback_query
import logging

if TYPE_CHECKING:
    from unicom.models import Channel

logger = logging.getLogger(__name__)


def handle_telegram_callback(channel: Channel, callback_query_data: dict):
    """
    Handle Telegram callback query (button click).

    Args:
        channel: The Telegram channel
        callback_query_data: Telegram callback query data including:
            - id: Unique callback query ID
            - data: CallbackExecution ID
            - from: User who clicked the button
            - message: The message containing the buttons

    Returns:
        bool: True if callback was processed, False if ignored
    """
    callback_id = callback_query_data.get('id')
    callback_execution_id = callback_query_data.get('data')
    from_user = callback_query_data.get('from', {})
    message_data = callback_query_data.get('message', {})

    print(f"🔘 CALLBACK DEBUG: Received callback query")
    print(f"   - Callback ID: {callback_id}")
    print(f"   - CallbackExecution ID: {callback_execution_id}")
    print(f"   - From User: {from_user.get('id')} (@{from_user.get('username')})")

    # Answer callback query immediately to stop loading indicator
    print(f"📞 CALLBACK DEBUG: Answering callback query to stop loading indicator")
    answer_callback_query(channel, callback_id)

    if not all([callback_id, callback_execution_id, from_user]):
        logger.warning(f"Invalid callback query data: missing required fields")
        print(f"❌ CALLBACK DEBUG: Missing required fields")
        return False

    # Lookup CallbackExecution
    try:
        execution = CallbackExecution.objects.select_related(
            'original_message', 'intended_account'
        ).get(id=callback_execution_id)
        print(f"✅ CALLBACK DEBUG: Found CallbackExecution: {execution.id}")
    except CallbackExecution.DoesNotExist:
        logger.warning(f"CallbackExecution not found: {callback_execution_id}")
        print(f"❌ CALLBACK DEBUG: CallbackExecution not found")
        return False

    # Check if expired
    if execution.is_expired():
        logger.info(f"CallbackExecution {execution.id} has expired")
        print(f"⏰ CALLBACK DEBUG: CallbackExecution has expired")
        return False

    # Get the clicking account
    user_id = str(from_user.get('id'))
    print(f"🔍 CALLBACK DEBUG: Looking for clicking account with ID: {user_id}")
    try:
        clicking_account = Account.objects.get(id=user_id, platform='Telegram')
        username = clicking_account.raw.get('username', clicking_account.name)
        print(f"✅ CALLBACK DEBUG: Found clicking account: {username}")
    except Account.DoesNotExist:
        logger.warning(f"Account not found for user: {user_id}")
        print(f"❌ CALLBACK DEBUG: Account not found")
        return False

    # Security check: Only the intended account can click
    if clicking_account.id != execution.intended_account.id:
        logger.info(f"Unauthorized button click by {username} on callback {execution.id}")
        print(f"❌ CALLBACK DEBUG: Account {username} is not the intended account")
        return False
    print(f"✅ CALLBACK DEBUG: Account is authorized")

    # Fire signal for project handlers
    try:
        print(f"📡 CALLBACK DEBUG: Firing telegram_callback_received signal")
        telegram_callback_received.send(
            sender=handle_telegram_callback,
            callback_execution=execution,
            clicking_account=clicking_account,
            original_message=execution.original_message,
            tool_call=execution.tool_call  # May be None
        )
        print(f"✅ CALLBACK DEBUG: Signal fired successfully")
        logger.info(f"Successfully processed callback {callback_id}")
        return True

    except Exception as e:
        logger.error(f"Error processing callback {callback_id}: {str(e)}", exc_info=True)
        print(f"❌ CALLBACK DEBUG: Error processing callback: {str(e)}")
        return False