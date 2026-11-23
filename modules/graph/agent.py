import json
import math
import pandas as pd
from typing import Literal
from pydantic import BaseModel, Field
from modules.graph.state import PipelineState
from modules.graph.router import route_after_diagnose, route_after_sandbox, route_after_validation, stop_reason
from modules.chat_models.planner import planning_model
from modules.chat_models.code import coding_model
from modules.chat_models.diagnose import diagnosing_model
from modules.storage.vault import download_decrypted, upload_encrypted
from modules.profiler.loader import load_table
from modules.profiler.profile import create_profile
from modules.sandbox.runner import run_sandbox, upload_dataframe, download_output
from langgraph.graph import StateGraph, START, END
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt
from langchain_core.messages import SystemMessage, HumanMessage

SAMPLE_ROWS = 500
MAX_ERRORS_IN_PROMPT = 10

PLANNER_PROMPT = """You plan how to clean a messy table so that it matches a target schema.
You get a profile of the data and the target schema. Map every target column to a source column,
list the transformations in order and anything a human must decide. Do not write code.
If a target column has no clearly matching source column, do not guess: add it to open_questions."""

CODER_PROMPT = """Write one Python function `transform(data)` that returns the cleaned DataFrame.
Every value in `data` is a string. `pd` and `np` are available, you may also `import re`.
No other imports, no file or network access, no printing. Output columns must exactly match
the target schema. Never drop rows, use empty strings for missing values."""

DIAGNOSE_PROMPT = """You diagnose why a data cleaning transformation failed.
fixable: a bug or missed format, give exact fix_instructions.
ambiguous: a human must decide, give one clear question.
impossible: the data cannot satisfy the rule.
Never suggest a fix that already failed in the attempt history."""

class Diagnosis(BaseModel):
    kind: Literal["fixable", "ambiguous", "impossible"]
    reason: str
    fix_instructions: str | None = Field(default = None)
    question: str | None = Field(default = None)

diagnoser = diagnosing_model.with_structured_output(Diagnosis)

def to_json(obj):
    return json.dumps(obj, indent = 2, default = str)

def check_schema(data: pd.DataFrame, schema: dict, rows_in: int):
    """Small validator: columns, required, numbers, dates and row count"""
    errors = []
    expected, actual = set(schema["columns"]), set(data.columns)

    if expected != actual:
        errors.append({"check": "columns", "missing": sorted(expected - actual), "extra": sorted(actual - expected)})
    if schema.get("row_count_preserved") and len(data) != rows_in:
        errors.append({"check": "row_count", "rows_in": rows_in, "rows_out": len(data)})

    for column, rules in schema["columns"].items():
        if column not in actual:
            continue
        values = data[column].astype(str).str.strip()
        filled = values[values != ""]

        bad = pd.Series(dtype = str)
        if rules.get("required"):
            bad = values[values == ""]
        if rules.get("type") in ("integer", "decimal"):
            bad = pd.concat([bad, filled[pd.to_numeric(filled, errors = "coerce").isna()]])
        if rules.get("type") == "date":
            parsed = pd.to_datetime(filled, format = rules.get("format", "%Y-%m-%d"), errors = "coerce")
            bad = pd.concat([bad, filled[parsed.isna()]])

        if len(bad):
            errors.append({
                "check": column,
                "failed": int(len(bad)),
                "examples": [{"row": int(i), "value": v} for i, v in bad.head(3).items()]
            })

    return {
        "passed": not errors,
        "error_count": sum(e.get("failed", 1) for e in errors),
        "errors": errors
    }

def profile(state: PipelineState):
    """Load the original file, profile it and upload sample and full copies for the sandbox"""
    raw = download_decrypted(state["vault_original_key"])
    data = load_table(raw, state["filename"])
    sample = data.sample(SAMPLE_ROWS, random_state = 0) if len(data) > SAMPLE_ROWS else data

    return {
        "profile": create_profile(data),
        "sample_key": upload_dataframe(sample, state["job_id"], "sample"),
        "full_key": upload_dataframe(data, state["job_id"], "full"),
        "iteration": 0,
        "status": "running"
    }

def planning(state: PipelineState):
    """Decide the column mapping and the transformations"""
    response = planning_model.invoke([
        SystemMessage(PLANNER_PROMPT),
        HumanMessage(f"PROFILE:\n{to_json(state['profile'])}\n\nTARGET SCHEMA:\n{to_json(state['schema'])}")
    ])

    return {"plan": response.content}

def coding(state: PipelineState):
    """Write the transform code, using the diagnosis and human answers on retries"""
    parts = [f"PLAN:\n{state['plan']}", f"TARGET SCHEMA:\n{to_json(state['schema'])}"]
    if state.get("code"):
        parts.append(f"PREVIOUS CODE:\n{state['code']}")
    if state.get("diagnosis"):
        parts.append(f"WHAT TO FIX:\n{state['diagnosis'].get('fix_instructions')}")
    if state.get("human_answers"):
        parts.append("HUMAN DECISIONS:\n" + "\n".join(state["human_answers"]))

    response = coding_model.invoke([
        SystemMessage(CODER_PROMPT),
        HumanMessage("\n\n".join(parts))
    ])

    return {"code": response.code, "iteration": state.get("iteration", 0) + 1}

def sandbox_runner(state: PipelineState):
    """Run the code on the sample inside the Lambda sandbox"""
    result = run_sandbox(state["code"], state["sample_key"], state["job_id"], state["iteration"])
    if not result["ok"]:
        return {
            "sandbox_result": result,
            "attempts": [{
                "iteration": state["iteration"],
                "code": state["code"],
                "error": result["error"],
                "error_count": math.inf
            }]
        }

    return {"sandbox_result": result}

def validation(state: PipelineState):
    """Check the sandbox output against the schema"""
    result = state["sandbox_result"]
    report = check_schema(download_output(result["output_key"]), state["schema"], result["rows_in"])

    return {
        "validation": report,
        "attempts": [{
            "iteration": state["iteration"],
            "code": state["code"],
            "error": None,
            "error_count": report["error_count"]
        }]
    }

def diagnosis(state: PipelineState):
    """Find why it failed and decide: fix, ask a human or give up"""
    result = state["sandbox_result"]
    if result["ok"]:
        failure = f"VALIDATION ERRORS:\n{to_json(state['validation']['errors'][:MAX_ERRORS_IN_PROMPT])}"
    else:
        failure = f"SANDBOX ERROR ({result['stage']}):\n{result['error']}\n{result['traceback']}"

    history = [{"iteration": a["iteration"], "error_count": a["error_count"]} for a in state.get("attempts", [])]

    response = diagnoser.invoke([
        SystemMessage(DIAGNOSE_PROMPT),
        HumanMessage(f"{failure}\n\nCURRENT CODE:\n{state['code']}\n\nATTEMPT HISTORY:\n{to_json(history)}")
    ])

    return {"diagnosis": response.model_dump()}

def ask_human(state: PipelineState):
    """Pause the graph until the human answers"""
    answer = interrupt({"question": state["diagnosis"]["question"]})
    return {"human_answers": [answer], "status": "running"}

def final_run(state: PipelineState):
    """Run the passing code once on the full file and check it again"""
    result = run_sandbox(state["code"], state["full_key"], state["job_id"], "full")
    if not result["ok"]:
        return {"sandbox_result": result, "status": "failed", "stop_reason": f"full_run_{result['stage']}"}

    report = check_schema(download_output(result["output_key"]), state["schema"], result["rows_in"])

    return {
        "sandbox_result": result,
        "validation": report,
        "status": "success" if report["passed"] else "partial"
    }

def report(state: PipelineState):
    """Store the cleaned file in the vault when the full run passed"""
    if state.get("status") != "success":
        return {"status": state.get("status") or "partial"}

    data = download_output(state["sandbox_result"]["output_key"])
    cleaned_key = upload_encrypted(data.to_csv(index = False).encode("utf-8"), state["job_id"], "cleaned.csv")

    return {"status": "success", "vault_cleaned_key": cleaned_key}

def stop(state: PipelineState):
    """End the run and record why"""
    return {"status": "failed", "stop_reason": stop_reason(state)}

graph = StateGraph(PipelineState)

graph.add_node("profile", profile)
graph.add_node("planning", planning)
graph.add_node("write_code", coding)
graph.add_node("sandbox", sandbox_runner)
graph.add_node("validate", validation)
graph.add_node("diagnose", diagnosis)
graph.add_node("ask_human", ask_human)
graph.add_node("final_run", final_run)
graph.add_node("report", report)
graph.add_node("stop", stop)

graph.add_edge(START, "profile")
graph.add_edge("profile", "planning")
graph.add_edge("planning", "write_code")
graph.add_edge("write_code", "sandbox")

graph.add_conditional_edges("sandbox", route_after_sandbox, ["validate", "diagnose", "stop"])
graph.add_conditional_edges("validate", route_after_validation, ["final_run", "diagnose", "stop"])
graph.add_conditional_edges("diagnose", route_after_diagnose, ["write_code", "ask_human", "report", "stop"])

graph.add_edge("ask_human", "write_code")
graph.add_edge("final_run", "report")
graph.add_edge("report", END)
graph.add_edge("stop", END)

# Background tasks run in other threads, so the connection is shared across threads
worker = graph.compile(checkpointer = SqliteSaver(sqlite3.connect("checkpoints.db", check_same_thread = False)))
