from pydantic import BaseModel, Field
from modules.chat_models.provider import get_chat_model

class TransformationCode(BaseModel):
    code: str = Field(description = "You are supposed to provide pandas code in def transform(data):")

coding_model = get_chat_model().with_structured_output(TransformationCode)
