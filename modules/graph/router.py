import math

MAX_ITERATIONS = 6

def is_stuck(attempts):
    """If the last 2 attempts didn't improve"""
    counts = [attempt["error_count"] for attempt in attempts]
    return len(counts) >= 3 and min(counts[-2:]) >= counts[-3]

def router_after_sandbox(state):
    result = state["sandbox_result"]
    if result["ok"]:
        return "validate"
    if result["stage"] == "invoke":
        return "stop"
    if state["iteration"] >= MAX_ITERATIONS or is_stuck(state["attempts"]):
        return "stop"
    return "diagnose"

def router_after_validation(state):
    if state["validation"]["passed"]:
        return "report"
    if state["iteration"] >= MAX_ITERATIONS or is_stuck(state["attempts"]):
        return "stop"
    return "diagnose"

def route_after_diagnose(state):
    return {
        "fixable": "write_code",
        "ambiguous": "ask_human",
        "impossible": "report"
    }.get(state["diagnosis"]["kind"], "stop")

def stop_reason(state):
    result = state.get("sandbox_result", {})
    if result.get("stage") == "invoke":
        return "invoke_error"
    if state["iteration"] >= MAX_ITERATIONS:
        return "max_iterations"
    if is_stuck(state.get("attempts", [])):
        return "stuck"
    return "unknown"
