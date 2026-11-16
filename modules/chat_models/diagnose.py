from core.config import setting
from langchain_openai.chat_models import ChatOpenAI

diagnosing_model = ChatOpenAI(model = setting.OPENAI_MODEL, api_key = setting.OPENAI_API_KEY)
