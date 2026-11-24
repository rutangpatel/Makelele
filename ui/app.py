import io
import os
import json
import time
import requests
import pandas as pd
import streamlit as st

POLL_SECONDS = 3
# Types the validator in modules/graph/agent.py understands
TYPES = ["string", "integer", "decimal", "date"]

# Label and badge color per job status
STATUS = {
    "running": ("Running", "blue", ":material/autorenew:"),
    "waiting_for_human": ("Needs your answer", "orange", ":material/help:"),
    "success": ("Success", "green", ":material/check_circle:"),
    "partial": ("Partial", "orange", ":material/warning:"),
    "failed": ("Failed", "red", ":material/error:")
}

def call_api(method: str, path: str, **kwargs):
    """Call the FastAPI app and stop the page if it can't be reached"""
    try:
        return requests.request(method, f"{st.session_state.api_url}{path}", timeout = 60, **kwargs)
    except requests.ConnectionError:
        st.error(f"Cannot reach the API at {st.session_state.api_url}. Is it running?", icon = ":material/cloud_off:")
        st.stop()

def preview(file):
    """First rows of the uploaded file, or None if pandas can't read it here"""
    buffer = io.BytesIO(file.getvalue())
    try:
        if file.name.lower().endswith((".xlsx", ".xls")):
            return pd.read_excel(buffer, dtype = str, keep_default_na = False, nrows = 20)
        return pd.read_csv(buffer, sep = "\t" if file.name.lower().endswith(".tsv") else ",", dtype = str, keep_default_na = False, nrows = 20)
    except Exception:
        return None

def build_schema(table: pd.DataFrame, keep_rows: bool):
    """Schema dict from the editor table, or an error message"""
    text = lambda v: "" if pd.isna(v) else str(v).strip()
    columns = {}
    for row in table.itertuples(index = False):
        name = text(row.column)
        if not name:
            continue
        if name in columns:
            return None, f"Column '{name}' is listed twice."
        rules = {"type": text(row.type) or "string"}
        # New rows can hold None, which bool() would not treat as unticked
        if pd.notna(row.required) and bool(row.required):
            rules["required"] = True
        if rules["type"] == "date" and text(row.format):
            rules["format"] = text(row.format)
        columns[name] = rules

    if not columns:
        return None, "Add at least one column."
    return {"columns": columns, "row_count_preserved": keep_rows}, None

def upload_view():
    """Pick a file and a schema, then start a job"""
    st.subheader("1. Upload a messy file")
    file = st.file_uploader("Messy file", type = ["csv", "tsv", "xlsx", "xls"], label_visibility = "collapsed")
    if not file:
        st.info("Upload a file to build its target schema.", icon = ":material/upload_file:")
        return

    data = preview(file)
    if data is None:
        st.caption("No preview for this file, the API will still check it. Add the target columns to the schema by hand.")
    else:
        st.caption(f"Preview of the first {len(data)} rows, {len(data.columns)} columns")
        st.dataframe(data, hide_index = True, height = 250)

    columns = [] if data is None else [str(c) for c in data.columns]
    draft = pd.DataFrame({"column": columns, "type": "string", "required": False, "format": ""})

    st.subheader("2. Define the target schema")
    st.caption("One row per column of the clean file, built from the file's headers. Rename, add or delete rows, pick each type and tick the required ones.")
    # Keyed by file so a new upload rebuilds the draft
    table = st.data_editor(
        draft,
        key = f"schema_{file.file_id}",
        num_rows = "dynamic",
        hide_index = True,
        use_container_width = True,
        column_config = {
            "column": st.column_config.TextColumn("Column", required = True),
            "type": st.column_config.SelectboxColumn("Type", options = TYPES, required = True, default = "string"),
            "required": st.column_config.CheckboxColumn("Required", default = False),
            "format": st.column_config.TextColumn("Date format", help = "Only for date columns, default %Y-%m-%d")
        }
    )
    keep_rows = st.toggle("Output keeps the same number of rows", value = True)

    schema, error = build_schema(table, keep_rows)
    if error:
        st.error(error, icon = ":material/table_edit:")
    else:
        with st.expander(f"Schema JSON ({len(schema['columns'])} columns)"):
            st.json(schema)

    if st.button("Start cleaning", type = "primary", icon = ":material/play_arrow:", disabled = error is not None, use_container_width = True):
        response = call_api("POST", "/jobs", files = {"file": (file.name, file.getvalue())}, data = {"schema": json.dumps(schema)})
        if response.status_code == 400:
            st.error(response.json()["detail"], icon = ":material/block:")
        elif not response.ok:
            st.error(f"API error {response.status_code}: {response.text}")
        else:
            st.session_state.job_id = response.json()["job_id"]
            st.rerun()

def attempts_view(attempts: list):
    """Chart, history table and generated code per attempt"""
    table = pd.DataFrame(attempts, columns = ["iteration", "error_count", "error", "code"])
    crashes = table[table["error_count"].isna()]["iteration"].tolist()
    chart, history, code = st.tabs([":material/show_chart: Errors per attempt", ":material/history: History", ":material/code: Code"])

    with chart:
        # The API sends infinite error counts (sandbox crashes) as null
        st.line_chart(table.dropna(subset = ["error_count"]), x = "iteration", y = "error_count", height = 280)
        if crashes:
            st.warning(f"Crashed in the sandbox at iteration: {', '.join(map(str, crashes))}", icon = ":material/bug_report:")

    with history:
        shown = table[["iteration", "error_count", "error"]].copy()
        shown["error_count"] = shown["error_count"].map(lambda v: "crash" if pd.isna(v) else str(int(v)))
        st.dataframe(shown, hide_index = True)

    with code:
        iteration = st.selectbox("Iteration", table["iteration"].tolist()[::-1])
        st.code(table[table["iteration"] == iteration]["code"].iloc[0], language = "python")

def job_view(job_id: str):
    """Show the job, ask the human, offer the download and poll while running"""
    response = call_api("GET", f"/jobs/{job_id}")
    # Right after upload the first checkpoint may not exist yet
    job = response.json() if response.ok else {"status": "running", "iteration": 0, "attempts": []}
    status = job["status"]
    label, color, icon = STATUS.get(status, (status, "gray", None))

    title, new = st.columns([4, 1], vertical_alignment = "center")
    title.subheader(f"Job `{job_id}`")
    if new.button("New job", icon = ":material/add:", use_container_width = True):
        del st.session_state.job_id
        st.rerun()
    st.badge(label, color = color, icon = icon)

    counts = [a["error_count"] for a in job["attempts"] if a["error_count"] is not None]
    with st.container(horizontal = True):
        st.metric("Iteration", job["iteration"], border = True)
        st.metric("Attempts", len(job["attempts"]), border = True)
        st.metric("Best error count", min(counts) if counts else "–", border = True)
        st.metric("Last error count", counts[-1] if counts else "–", border = True)

    if status == "waiting_for_human":
        with st.container(border = True):
            st.markdown("#### :material/help: The agent needs a decision")
            st.info(job["question"])
            with st.form("answer", border = False):
                answer = st.text_area("Your answer", placeholder = "Type your decision for the agent")
                if st.form_submit_button("Send answer", type = "primary", icon = ":material/send:") and answer.strip():
                    call_api("POST", f"/jobs/{job_id}/answer", data = {"answer": answer})
                    # shortcut: give the resumed run a moment to clear the interrupt, poll the status instead if the question reappears
                    time.sleep(1)
                    st.rerun()

    elif status == "success" and job["has_download"]:
        st.success("The file is clean and matches the schema.", icon = ":material/check_circle:")
        data = call_api("GET", f"/jobs/{job_id}/download").content
        st.download_button("Download cleaned CSV", data, file_name = f"{job_id}_cleaned.csv", mime = "text/csv", type = "primary", icon = ":material/download:")

    elif status in ("failed", "partial"):
        st.error(f"**Stopped ({label.lower()})**: {job.get('stop_reason') or job.get('error') or 'no reason given'}", icon = ":material/report:")

    if job["attempts"]:
        attempts_view(job["attempts"])

    if status == "running":
        with st.spinner("The agent is working, refreshing every few seconds..."):
            time.sleep(POLL_SECONDS)
        st.rerun()

st.set_page_config(page_title = "Makelele", page_icon = ":material/cleaning_services:", layout = "wide")
st.title(":material/cleaning_services: Makelele")
st.caption("Upload a messy spreadsheet and a target schema. The agent writes the cleaning code, tests it in a sandbox and fixes it until it passes.")

with st.sidebar:
    st.header("Settings")
    st.session_state.api_url = st.text_input("API base URL", os.getenv("MAKELELE_API_URL", "http://localhost:8000")).rstrip("/")
    if "job_id" in st.session_state:
        st.caption(f"Current job: `{st.session_state.job_id}`")

if "job_id" in st.session_state:
    job_view(st.session_state.job_id)
else:
    upload_view()
