import io
import json
import math
import uuid
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from modules.graph.agent import worker
from modules.profiler.loader import load_table, InvalidSpreadsheetError
from modules.storage.vault import upload_encrypted, download_decrypted

app = FastAPI(title = "Makelele")

def config(job_id: str):
    """LangGraph config for one job"""
    return {"configurable": {"thread_id": job_id}}

def run_graph(job_input, job_id: str):
    """Run or resume the graph; errors are kept in the checkpoint"""
    try:
        worker.invoke(job_input, config = config(job_id))
    except Exception:
        pass

def get_snapshot(job_id: str):
    """Load the job's checkpoint or 404"""
    snapshot = worker.get_state(config(job_id))
    if not snapshot.values:
        raise HTTPException(status_code = 404, detail = "Job not found")
    return snapshot

@app.post("/jobs")
async def create_job(background_tasks: BackgroundTasks, file: UploadFile = File(...), schema_json: str = Form(..., alias = "schema")):
    """Check the file, encrypt it into the vault and start the graph"""
    try:
        schema = json.loads(schema_json)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code = 400, detail = f"Schema is not valid JSON: {e}")
    if not isinstance(schema, dict) or not isinstance(schema.get("columns"), dict):
        raise HTTPException(status_code = 400, detail = "Schema needs a 'columns' object")

    data = await file.read()
    try:
        load_table(data, file.filename)
    except InvalidSpreadsheetError as e:
        raise HTTPException(status_code = 400, detail = str(e))

    job_id = uuid.uuid4().hex[:12]
    key = upload_encrypted(data, job_id)
    job_input = {"job_id": job_id, "filename": file.filename, "vault_original_key": key, "schema": schema}
    background_tasks.add_task(run_graph, job_input, job_id)

    return {"job_id": job_id}

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Status, iteration, attempts and the pending question"""
    snapshot = get_snapshot(job_id)
    values = snapshot.values
    status, question, error = values.get("status", "running"), None, None

    if snapshot.interrupts:
        status, question = "waiting_for_human", snapshot.interrupts[0].value["question"]
    elif errors := [t.error for t in snapshot.tasks if t.error]:
        status, error = "failed", repr(errors[0])

    # A sandbox crash stores error_count as inf, which JSON can't hold
    attempts = [{**a, "error_count": None if math.isinf(a["error_count"]) else a["error_count"]} for a in values.get("attempts", [])]

    return {
        "job_id": job_id,
        "status": status,
        "iteration": values.get("iteration", 0),
        "attempts": attempts,
        "question": question,
        "stop_reason": values.get("stop_reason"),
        "error": error,
        "has_download": bool(values.get("vault_cleaned_key"))
    }

@app.post("/jobs/{job_id}/answer")
def answer_job(job_id: str, background_tasks: BackgroundTasks, answer: str = Form(...)):
    """Resume a job paused at ask_human"""
    if not get_snapshot(job_id).interrupts:
        raise HTTPException(status_code = 409, detail = "Job is not waiting for an answer")
    background_tasks.add_task(run_graph, Command(resume = answer), job_id)

    return {"job_id": job_id, "status": "running"}

@app.get("/jobs/{job_id}/download")
def download_job(job_id: str):
    """Decrypt the cleaned CSV in memory and stream it"""
    key = get_snapshot(job_id).values.get("vault_cleaned_key")
    if not key:
        raise HTTPException(status_code = 409, detail = "No cleaned file for this job")

    return StreamingResponse(
        io.BytesIO(download_decrypted(key)),
        media_type = "text/csv",
        headers = {"Content-Disposition": f'attachment; filename="{job_id}_cleaned.csv"'}
    )
