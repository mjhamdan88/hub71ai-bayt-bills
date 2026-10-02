from django.core.exceptions import ObjectDoesNotExist
from unibot.models import Bot, Tool
from typing import Optional, List
import reversion
from unibot.services.tool_exceptions import ToolHandlerError

def update_bot(bot_id: int, name: Optional[str] = None, code: Optional[str] = None, 
               tool_ids: Optional[List[int]] = None) -> dict:
    """Updates an existing bot"""
    try:
        with reversion.create_revision():
            bot = Bot.objects.get(id=bot_id)
            if name:
                bot.name = name
            if code:
                bot.code = code
            bot.save()
            if tool_ids is not None:
                tools = Tool.objects.filter(id__in=tool_ids)
                bot.tools.set(tools)
            reversion.set_comment("Programmatic update via update_bot tool")
        return {"bot_id": bot.id}
    except ObjectDoesNotExist:
        raise ToolHandlerError(f"Bot with ID {bot_id} not found")
    except Exception as e:
        raise ToolHandlerError(str(e))

tool_definition = {
    "name": "update_bot",
    "description": "Update an existing bot",
    "parameters": {
        "bot_id": {
            "type": "integer",
            "description": "ID of the bot to update"
        },
        "name": {
            "type": "string",
            "description": "New name for the bot",
            "default": None
        },
        "code": {
            "type": "string",
            "description": "New Python code",
            "default": None
        },
        "tool_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "New list of tool IDs",
            "default": None
        }
    },
    "run": update_bot
} 
