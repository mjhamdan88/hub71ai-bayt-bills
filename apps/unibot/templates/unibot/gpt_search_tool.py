# GPT Search Tool - Intelligent Web Search Agent
#
# This tool provides access to OpenAI's GPT search preview model, which is an intelligent
# web search agent that can perform real-time web searches and provide comprehensive answers.
# 
# IMPORTANT: This is NOT a simple keyword search tool. It's an intelligent agent that:
# - Understands complex search requirements and context
# - Performs multiple searches if needed to gather comprehensive information
# - Synthesizes information from multiple sources
# - Provides well-structured, relevant responses
#
# Input should be specific search criteria and requirements, not just keywords.

from unibot.services.tool_exceptions import ToolHandlerError

def gpt_search(search_query: str) -> str:
    """
    Performs intelligent web search using OpenAI's GPT search preview model.
    
    This is an intelligent search agent that understands context and provides comprehensive
    answers by searching the web and synthesizing information from multiple sources.
    
    Args:
        search_query: Specific search criteria and requirements. Should be detailed and 
                     contextual rather than just keywords. The agent works best with 
                     clear, specific questions or research requirements.
    
    Returns:
        Comprehensive search results and analysis from the GPT search agent.
    """
    try:
        # Use the GPT search preview model
        response = openai_client.chat.completions.create(
            model="gpt-4o-search-preview",
            messages=[
                {
                    "role": "system", 
                    "content": """You are an intelligent web search agent. When given a search query, you should:
1. Perform comprehensive web searches to gather relevant, up-to-date information
2. Synthesize information from multiple reliable sources
3. Provide well-structured, accurate responses
4. Keep responses concise but comprehensive unless specifically asked for detailed analysis
5. Always cite or reference your sources when possible
6. Focus on factual, verifiable information

Keep your responses focused and avoid unnecessary verbosity unless the query specifically requires detailed analysis."""
                },
                {
                    "role": "user", 
                    "content": search_query
                }
            ],
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        # Surface handled error so conversation continues
        raise ToolHandlerError(f"Error performing search: {str(e)}")


tool_definition = {
    "name": "gpt_search",
    "description": "Intelligent web search agent using OpenAI's GPT search capabilities. This is NOT a simple keyword search - it's an intelligent agent that understands context, performs comprehensive research, and synthesizes information from multiple sources. Provide specific search criteria and requirements rather than just keywords. The agent excels at answering complex questions, finding current information, and providing well-researched responses.",
    "parameters": {
        "search_query": {
            "type": "string",
            "description": "Specific search criteria and requirements. Should be detailed and contextual (e.g., 'Find the latest developments in quantum computing applications for cryptography in 2024' rather than just 'quantum computing'). The more specific and detailed the query, the better the results."
        }
    },
    "run": gpt_search
}
