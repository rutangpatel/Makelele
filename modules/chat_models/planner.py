from pydantic import BaseModel, Field
from modules.chat_models.provider import get_chat_model

class ColumnMatch(BaseModel):
    target: str = Field(description = "Target schema column")
    source: str | None = Field(description = "Exact source column name, or null if none matches")
    reason: str = Field(description = "Why this source column matches the target")

class CleaningPlan(BaseModel):
    mapping: list[ColumnMatch]
    steps: list[str]
    open_questions: list[str] = Field(default_factory = list)

planning_model = get_chat_model().with_structured_output(CleaningPlan)
