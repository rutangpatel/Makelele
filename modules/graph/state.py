import operator
from typing_extensions import TypedDict
from typing import Annotated, Literal
from langgraph.graph.message import add_messages

class Attempt(TypedDict):
    iteration: int
    code: str
    error: str | None
    error_count: float

class PipelineState(TypedDict):
    # Job Identity
    job_id: str
    filename: str
    vault_original_key: str

    # Definition of Clean
    schema: dict

    # Planner
    profile: dict
    plan: dict
    unconfirmed_mapping: list[dict]

    # Loop
    iteration: int
    code: str
    sample_key: str
    full_key: str
    sandbox_result: dict
    validation: dict
    attempts: Annotated[list[Attempt], operator.add]
    diagnosis: dict

    # Human in the loop
    human_answers: Annotated[list[str], operator.add]

    # Outcome
    status: Literal["running", "waiting_for_human", "success", "partial", "failed"]
    stop_reason: str | None
    vault_cleaned_key: str | None
