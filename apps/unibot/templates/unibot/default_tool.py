# Default tool template for new Tool.code fields
#
# CONTEXT VARIABLES AVAILABLE IN TOOL CODE:
# - bot: The Bot instance processing this request
# - message: The Message object being processed  
# - account: The Account/user who sent the message (message.sender)
# - request: The Request object containing status, category, etc.
# - member: The Member object if available (request.member)
# - openai_client: OpenAI client instance
#
# You can access these variables directly in your tool functions:
# - request.id, request.status, request.category_id
# - message.content, message.sender
# - account.username, account.email
# - member.id (if available)

import requests
from bs4 import BeautifulSoup
import re
from unibot.services.tool_exceptions import ToolHandlerError

def summarize_webpage(url: str, max_sentences: int = 3) -> str:
    """
    Fetches the web page at the given URL and returns a summary of its content.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        # Remove scripts/styles
        for tag in soup(['script', 'style']):
            tag.decompose()
        text = soup.get_text(separator=' ')
        # Collapse whitespace and split into sentences
        text = re.sub(r'\s+', ' ', text)
        sentences = re.split(r'(?<=[.!?]) +', text)
        summary = ' '.join(sentences[:max_sentences])
        return summary if summary else 'No summary could be generated.'
    except Exception as e:
        # Surface a handled error to the LLM without breaking the conversation
        raise ToolHandlerError(f"Error fetching or summarizing the web page: {e}")


tool_definition = {
    "name": "summarize_webpage",
    "description": "Fetches a web page and returns a summary of its content.",
    "parameters": {
        "url": {
            "type": "string", 
            "description": "The URL of the web page to summarize."
        },
        "max_sentences": {
            "type": "integer", 
            "description": "Maximum number of sentences in the summary.", 
            "default": 3
        }
    },
    "run": summarize_webpage
} 
