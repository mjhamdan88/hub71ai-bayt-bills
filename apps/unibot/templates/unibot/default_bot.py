def handle_incoming_message(message, bot, tools_list):
    # Available globals: bot, message, account, request, member (if available), openai_client
    return bot.reply_using_llm(
        message, 
        tools_list,
        system_instruction="You are Insightifyr AI, a powerful AI capable of browsing the web",
        request=request  # Pass request object to make it available in tools
    )