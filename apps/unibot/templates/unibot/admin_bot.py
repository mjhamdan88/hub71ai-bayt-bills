import json
import os
from typing import Dict, Any, List
from unibot.models import Bot, Tool


def handle_incoming_message(message, bot, tools_list):
    """
    Admin bot that handles CRUD operations for bots and tools.
    First analyzes the request to determine needed operations and context,
    then executes the operations using appropriate tools.
    """
    # Get list of existing bots
    existing_bots = [
        {"id": b.id, "name": b.name}
        for b in Bot.objects.all()
    ]

    # Define the JSON schema for the analysis response
    analysis_schema = {
        "type": "object",
        "properties": {
            "bots_involved": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "List of bot IDs that their full information and source code "
                    "needs to be inspected. Maximum 3 bots."
                )
            },
            "tools_involved": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "List of tool IDs that their full information and source code "
                    "needs to be inspected. Maximum 3 tools."
                )
            },
            "operations": {
                "type": "object",
                "properties": {
                    "bot_operations": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["create_bot", "update_bot", "delete_bot"]
                        }
                    },
                    "tool_operations": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["create_tool", "update_tool", "delete_tool"]
                        }
                    }
                }
            }
        }
    }

    # First, analyze the request using a direct API call
    system_prompt = f"""
        You are an admin assistant that analyzes requests about managing bots and tools.
        Your task is to determine:
        1. Which existing bots and tools need to be inspected (by their IDs, max 3 each)
        2. What operations need to be performed

        Existing bots in the system:
        {chr(10).join(f"- Bot {b['id']}: {b['name']}" for b in existing_bots)}

        Respond with a JSON object following this structure:
        {{
            "bots_involved": [list of bot IDs to inspect],
            "tools_involved": [list of tool IDs to inspect],
            "operations": {{
                "bot_operations": [list from: "create_bot", "update_bot", "delete_bot"],
                "tool_operations": [list from: "create_tool", "update_tool", "delete_tool"]
            }}
        }}

        Example 1:
        "I need to update bot 5 and create a new tool for it"
        {{
            "bots_involved": [5],
            "tools_involved": [],
            "operations": {{
                "bot_operations": ["update_bot"],
                "tool_operations": ["create_tool"]
            }}
        }}
    """.strip()

    model = "gpt-4o-mini-audio-preview" if message.media_type == "audio" else "gpt-4o-mini"

    analysis_function = {
        "type": "function",  # indicates a function tool
        "function": {
            "name": "analysis_response",  # arbitrary function name
            "description": (
                "Returns a structured analysis of the admin user's request, "
                "including which existing bots/tools are relevant and which "
                "operations should be performed."
            ),
            "parameters": analysis_schema,
        },
    }

    analysis_response = openai_client.chat.completions.create(
        model=model,
        tools=[analysis_function],
        tool_choice={"type": "function", "function": {"name": "analysis_response"}},  # force the function call
        messages=message.as_llm_chat(
            mode="thread",
            system_instruction=system_prompt,
        ),
    )

    analysis: Dict[str, Any] = {}

    try:
        tool_calls = analysis_response.choices[0].message.tool_calls  # type: ignore[attr-defined]
        if tool_calls:
            args_str = tool_calls[0].function.arguments  # type: ignore[index]
            analysis = json.loads(args_str)
        else:
            # Fallback: try to parse the raw content (text models without tool calls)
            analysis_str = analysis_response.choices[0].message.content or "{}"
            analysis = json.loads(analysis_str)
    except (AttributeError, json.JSONDecodeError, IndexError, TypeError):
        # Any failure results in an empty analysis dict to keep flow resilient
        analysis = {}
    
    context_parts = []
    
    # Add template readmes if needed for creation/updates
    if analysis.get("operations", {}).get("bot_operations", []):
        ops = analysis["operations"]["bot_operations"]
        if "create_bot" in ops or "update_bot" in ops:
            context_parts.append("\n\n" + Bot.get_template_readme())
    
    if analysis.get("operations", {}).get("tool_operations", []):
        ops = analysis["operations"]["tool_operations"]
        if "create_tool" in ops or "update_tool" in ops:
            context_parts.append("\n\n" + Tool.get_template_readme())
    
    # Add info about involved bots and tools
    for bot_id in analysis.get("bots_involved", []):
        try:
            bot = Bot.objects.get(id=bot_id)
            context_parts.append(f"\n\n{bot.info}")
        except Bot.DoesNotExist:
            pass
            
    for tool_id in analysis.get("tools_involved", []):
        try:
            tool = Tool.objects.get(id=tool_id)
            context_parts.append(f"\n\n{tool.info}")
        except Tool.DoesNotExist:
            pass

    # Filter tools based on needed operations
    needed_tools = []
    for op in analysis.get("operations", {}).get("bot_operations", []):
        needed_tools.extend(
            t for t in tools_list 
            if t.get_definition(bot=bot, message=message, openai_client=openai_client, request=request)["name"] == op
        )
    for op in analysis.get("operations", {}).get("tool_operations", []):
        needed_tools.extend(
            t for t in tools_list 
            if t.get_definition(bot=bot, message=message, openai_client=openai_client, request=request)["name"] == op
        )

    # Build final system instruction with proper string handling
    base_instruction = "You are Admin AI; a helpful assistant that helps manage bots and tools."
    
    context_section = ""
    if context_parts:
        context_section = "\n\nYou have access to the following context about existing bots, tools, and templates:\n\n"
        context_section += "\n".join(context_parts)
    
    operation_section = ""
    if needed_tools:
        operation_section = (
            "\n\nExecute the necessary operations based on the user's request using the provided tools. "
            "For any create/update operations, follow the templates provided in the context."
        )
    else:
        operation_section = "\n\nRespond to the user's request in a helpful and friendly manner."
    
    system_instruction = (base_instruction + context_section + operation_section).strip()

    # Use bot's reply_using_llm with filtered tools and context
    return bot.reply_using_llm(
        message,
        tools_list=needed_tools,
        system_instruction=system_instruction,
        request=request
    )
