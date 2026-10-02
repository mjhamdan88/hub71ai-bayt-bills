from django.core.exceptions import ObjectDoesNotExist
from unibot.models import Tool
from typing import Optional
import reversion
from unibot.services.tool_exceptions import ToolHandlerError

def update_tool(tool_id: int, name: Optional[str] = None, code: Optional[str] = None) -> dict:
    """Updates an existing tool"""
    try:
        with reversion.create_revision():
            tool = Tool.objects.get(id=tool_id)
            if name:
                tool.name = name
            if code:
                tool.code = code
            tool.save()
            reversion.set_comment("Programmatic update via update_tool tool")
        return {"tool_id": tool.id}
    except ObjectDoesNotExist:
        raise ToolHandlerError(f"Tool with ID {tool_id} not found")
    except Exception as e:
        raise ToolHandlerError(str(e))

tool_definition = {
    "name": "update_tool",
    "description": "Update an existing tool",
    "parameters": {
        "tool_id": {
            "type": "integer",
            "description": "ID of the tool to update"
        },
        "name": {
            "type": "string",
            "description": "New name for the tool",
            "default": None
        },
        "code": {
            "type": "string",
            "description": "New Python code",
            "default": None
        }
    },
    "run": update_tool
} 
