import os
import json
import time
import requests
import pandas as pd
import streamlit as st

POLL_SECONDS = 3

PRESETS = {
    "Employee dataset": {
        "columns": {
            "Employee_ID": {"type": "string", "required": True},
            "First_Name": {"type": "string", "required": True},
            "Last_Name": {"type": "string", "required": True},
            "Age": {"type": "integer"},
            "Department": {"type": "string", "required": True},
            "Region": {"type": "string", "required": True},
            "Status": {"type": "string"},
            "Join_Date": {"type": "date", "format": "%Y-%m-%d"},
            "Salary": {"type": "decimal"},
            "Email": {"type": "string"},
            "Phone": {"type": "string"},
            "Performance_Score": {"type": "string"},
            "Remote_Work": {"type": "string"}
        },
        "row_count_preserved": True
    },
    "Vendor amounts": {
        "columns": {
            "vendor": {"type": "string", "required": True},
            "amount": {"type": "decimal"}
        },
        "row_count_preserved": True
    },
    "Empty": {"columns": {}, "row_count_preserved": True}
}

def call_api(method: str, path: str, **kwargs):
    """Call the FastAPI app and stop the page if it can't be reached"""
    try:
        return requests.request(method, f"{st.session_state.api_url}{path}", timeout = 60, **kwargs)
    except requests.ConnectionError:
        st.error(f"Cannot reach the API at {st.session_state.api_url}. Is it running?")
        st.stop()

def upload_view():
    """Pick a file and a schema, then start a job"""
    st.header("Upload")
    file = st.file_uploader("Messy file", type = ["csv", "tsv", "xlsx", "xls"])
    preset = st.selectbox("Schema preset", list(PRESETS))
    schema = st.text_area("Schema (JSON)", json.dumps(PRESETS[preset], indent = 2), height = 400, key = f"schema_{preset}")

    if st.button("Start cleaning", type = "primary", disabled = file is None):
        response = call_api("POST", "/jobs", files = {"file": (file.name, file.getvalue())}, data = {"schema": schema})
        if response.status_code == 400:
            st.error(response.json()["detail"])
        elif not response.ok:
            st.error(f"API error {response.status_code}: {response.text}")
        else:
            st.session_state.job_id = response.json()["job_id"]
            st.rerun()

def attempts_view(attempts: list):
    """Chart of error_count per attempt and the history table"""
    table = pd.DataFrame(attempts, columns = ["iteration", "error_count", "error"])
    crashes = table[table["error_count"].isna()]["iteration"].tolist()

    # The API sends infinite error counts (sandbox crashes) as null
    st.line_chart(table.dropna(subset = ["error_count"]), x = "iteration", y = "error_count")
    if crashes:
        st.warning(f"Crashed in the sandbox at iteration: {', '.join(map(str, crashes))}")

    table["error_count"] = table["error_count"].map(lambda v: "crash" if pd.isna(v) else str(int(v)))
    st.dataframe(table, hide_index = True)

def job_view(job_id: str):
    """Show the job, ask the human, offer the download and poll while running"""
    st.header(f"Job {job_id}")
    if st.button("New job"):
        del st.session_state.job_id
        st.rerun()

    response = call_api("GET", f"/jobs/{job_id}")
    # Right after upload the first checkpoint may not exist yet
    job = response.json() if response.ok else {"status": "running", "iteration": 0, "attempts": []}
    status = job["status"]

    left, right = st.columns(2)
    left.metric("Status", status)
    right.metric("Iteration", job["iteration"])

    if job["attempts"]:
        attempts_view(job["attempts"])

    if status == "waiting_for_human":
        st.info(job["question"])
        with st.form("answer"):
            answer = st.text_area("Your answer")
            if st.form_submit_button("Submit answer") and answer.strip():
                call_api("POST", f"/jobs/{job_id}/answer", data = {"answer": answer})
                # shortcut: give the resumed run a moment to clear the interrupt, poll the status instead if the question reappears
                time.sleep(1)
                st.rerun()

    elif status == "success" and job["has_download"]:
        st.success("The file is clean.")
        data = call_api("GET", f"/jobs/{job_id}/download").content
        st.download_button("Download cleaned CSV", data, file_name = f"{job_id}_cleaned.csv", mime = "text/csv")

    elif status in ("failed", "partial"):
        st.error(f"Stopped ({status}): {job.get('stop_reason') or job.get('error') or 'no reason given'}")

    elif status == "running":
        time.sleep(POLL_SECONDS)
        st.rerun()

st.set_page_config(page_title = "Makelele", layout = "wide")
st.session_state.api_url = st.sidebar.text_input("API base URL", os.getenv("MAKELELE_API_URL", "http://localhost:8000")).rstrip("/")

if "job_id" in st.session_state:
    job_view(st.session_state.job_id)
else:
    upload_view()
