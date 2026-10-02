from unibot.models import Bot, Tool
import reversion
from unibot.services.tool_exceptions import ToolHandlerError

def create_bot(name: str, code: str, tool_ids: list[int] = None) -> dict:
    """Creates a new bot with specified tools"""
    try:
        with reversion.create_revision():
            bot = Bot.objects.create(
                name=name,
                category=f"{name} category",
                code=code
            )
            if tool_ids:
                tools = Tool.objects.filter(id__in=tool_ids)
                bot.tools.set(tools)
            reversion.set_comment("Initial revision via create_bot tool")
        return {"bot_id": bot.id}
    except Exception as e:
        raise ToolHandlerError(str(e))

tool_definition = {
    "name": "create_bot",
    "description": "Create a new bot",
    "parameters": {
        "name": {
            "type": "string",
            "description": "Name of the bot"
        },
        "code": {
            "type": "string",
            "description": "Python code for the bot"
        },
        "tool_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "List of tool IDs to assign to the bot",
            "default": []
        }
    },
    "run": create_bot
} 
