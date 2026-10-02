from django.conf import settings
from openai import OpenAI


def handle_incoming_message(message, bot, tools_list):
    return bot.reply_using_llm(
        message,
        tools_list,
        model_default=settings.PORTACODE_LLM_MODEL,
        api_mode="responses",
        openai_client=OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        ),
        system_instruction="You are a helpful assistant.",
        request=request,
    )
