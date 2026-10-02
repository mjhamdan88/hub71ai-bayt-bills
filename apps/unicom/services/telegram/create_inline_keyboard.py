# unicom.services.telegram.create_inline_keyboard.py
from typing import List, Dict, Any, Union


def create_inline_keyboard_button(text: str, **kwargs) -> Dict[str, str]:
    """
    Helper function to create an inline keyboard button.

    Args:
        text: Button text to display
        **kwargs: One of the following button types:
            - callback_data: Data to be sent in a callback query
            - url: HTTP or tg:// URL to open
            - switch_inline_query: Inline query to insert in the input field
            - switch_inline_query_current_chat: Inline query for current chat
            - pay: True for payment button

    Returns:
        Button dictionary ready for Telegram API

    Example:
        create_inline_keyboard_button("Visit Website", url="https://example.com")
        create_inline_keyboard_button("Click Me", callback_data="button_clicked")
    """
    button = {"text": text}

    # Validate that exactly one button type is provided
    valid_types = ['callback_data', 'url', 'switch_inline_query', 'switch_inline_query_current_chat', 'pay']
    provided_types = [key for key in kwargs.keys() if key in valid_types]

    if len(provided_types) != 1:
        raise ValueError(f"Exactly one button type must be provided: {valid_types}")

    button.update(kwargs)
    return button


def create_inline_keyboard(buttons: List[List[Dict[str, Any]]]) -> Dict[str, List[List[Dict[str, str]]]]:
    """
    Helper function to create a properly formatted inline keyboard for reply_markup.

    Args:
        buttons: List of button rows, where each row is a list of button specifications.
                Each button can be either:
                - A dict with 'text' and button type (callback_data, url, etc.)
                - A dict ready for Telegram API

    Returns:
        Properly formatted reply_markup dict for Telegram API

    Example:
        create_inline_keyboard([
            [{"text": "Button 1", "callback_data": "btn1"}, {"text": "URL", "url": "https://example.com"}],
            [{"text": "Button 2", "callback_data": "btn2"}]
        ])
    """
    return {"inline_keyboard": buttons}


def create_callback_button(text: str, callback_data: Any, message=None, account=None, tool_call=None, expires_at=None) -> Dict[str, str]:
    """
    Quick helper to create a callback button.

    Args:
        text: Button text to display
        callback_data: Any JSON-serializable data (dict, list, str, int, bool, None)
        message: The message this button belongs to (optional, for creating CallbackExecution)
        account: The intended account for this button (optional, defaults to message recipient)
        tool_call: Optional ToolCall to link this button to (for tool-generated buttons)
        expires_at: Optional expiration datetime for this callback

    Returns:
        Button dictionary ready for Telegram API

    Examples:
        create_callback_button("Yes", "confirm")
        create_callback_button("Buy", {"product_id": 123}, message=msg, account=user_account)
        create_callback_button("Confirm", {"action": "confirm"}, message=msg, tool_call=tool_call_obj)
    """
    # If message is provided, create CallbackExecution and use its ID
    if message:
        from unicom.models import CallbackExecution

        # Default to message sender if no account specified
        if not account:
            if message.is_outgoing:
                # For outgoing messages, find the first account in the chat
                from unicom.models import AccountChat
                account_chat = AccountChat.objects.filter(chat=message.chat).first()
                account = account_chat.account if account_chat else message.sender
            else:
                account = message.sender

        execution = CallbackExecution.objects.create(
            original_message=message,
            callback_data=callback_data,
            intended_account=account,
            tool_call=tool_call,
            expires_at=expires_at
        )
        callback_data_str = str(execution.id)
    else:
        # Legacy: just convert callback_data to string
        import json
        if not isinstance(callback_data, str):
            callback_data_str = json.dumps(callback_data, separators=(',', ':'))
        else:
            callback_data_str = callback_data

    return create_inline_keyboard_button(text, callback_data=callback_data_str)


def create_url_button(text: str, url: str) -> Dict[str, str]:
    """
    Quick helper to create a URL button.

    Args:
        text: Button text to display
        url: URL to open when button is pressed

    Returns:
        Button dictionary ready for Telegram API
    """
    return create_inline_keyboard_button(text, url=url)


def create_simple_keyboard(*button_texts_and_data) -> Dict[str, List[List[Dict[str, str]]]]:
    """
    Quick helper to create a simple single-row keyboard with callback buttons.

    Args:
        *button_texts_and_data: Pairs of (text, callback_data) or single dicts

    Returns:
        reply_markup dict ready for Telegram API

    Example:
        create_simple_keyboard("Yes", "yes_action", "No", "no_action")
        create_simple_keyboard({"text": "Custom", "url": "https://example.com"})
    """
    buttons = []

    i = 0
    while i < len(button_texts_and_data):
        item = button_texts_and_data[i]

        if isinstance(item, dict):
            # It's already a button dict
            buttons.append(item)
            i += 1
        elif i + 1 < len(button_texts_and_data) and isinstance(button_texts_and_data[i + 1], str):
            # It's a text, callback_data pair
            text = item
            callback_data = button_texts_and_data[i + 1]
            buttons.append(create_callback_button(text, callback_data))
            i += 2
        else:
            raise ValueError(f"Invalid button specification at position {i}")

    return create_inline_keyboard([buttons])