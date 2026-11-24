from core.config import get_secret
from langchain_openai.chat_models import ChatOpenAI

def get_chat_model():
    return ChatOpenAI(model = get_secret("OPENAI_MODEL"), api_key = get_secret("OPENAI_API_KEY"))
