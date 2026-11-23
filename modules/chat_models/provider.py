from core.config import setting
from langchain_openai.chat_models import ChatOpenAI

def get_chat_model():
    return ChatOpenAI(model = setting.OPENAI_MODEL, api_key = setting.OPENAI_API_KEY)
