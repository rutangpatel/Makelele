import io
import json
import uuid
import pandas as pd
from functools import lru_cache
from core.config import setting
from modules.aws.s3 import get_s3_client
from modules.aws.lambda_client import get_lambda

FUNCTION_NAME = "makelele-sandbox"
INPUT_PREFIX = "Input"
OUTPUT_PREFIX = "Output"


@lru_cache
def s3():
    return get_s3_client()

@lru_cache
def lam():
    return get_lambda()

def new_run_id():
    return uuid.uuid4().hex[:12]

def upload_input(data: bytes, run_id: str, iteration: int):
    key = f"{INPUT_PREFIX}/{run_id}/{iteration}.csv"
    s3().put_object(
        Bucket = setting.BUCKET_NAME,
        Key = key,
        Body = data,
        ContentType = "text/csv"
    )

    return key

def upload_dataframe(data: pd.DataFrame, run_id: str, iteration: int):
    return upload_input(data.to_csv(index = False).encode("utf-8"), run_id, iteration)

def download_output(key: str):
    body = s3().get_object(Bucket = setting.BUCKET_NAME, Key = key)["Body"].read()
    return pd.read_csv(io.BytesIO(body), dtype = str, keep_default_na = False)

def run_sandbox(code: str, input_key: str, run_id: str, iteration: int):
    output_key = f"{OUTPUT_PREFIX}/{run_id}/{iteration}.csv"
    payload = {"code": code, "input_key": input_key, "output_key": output_key}

    try:
        response = lam().invoke(
            FunctionName = FUNCTION_NAME,
            InvocationType = "RequestResponse",
            Payload = json.dumps(payload).encode("utf-8")
        )
    except Exception as e:
        return {
            "ok": False,
            "stage": "invoke",
            "error": f"{type(e).__name__}: {e}",
            "traceback": ""
        }

    result = json.loads(response["Payload"].read() or b"{}")

    if "FunctionError" in response:
        return {
            "ok": False,
            "stage": "lambda",
            "error": f"{result.get("errorType", "Unknown")}: {result.get("errorMessage", "")}",
            "traceback": "\n".join(result.get("stackTrace", []))[-2000:]
        }

    if not result.get("ok"):
        return {
            "ok": False,
            "stage": "code",
            "error": result.get("error", "Unknown Error"),
            "traceback": result.get("traceback", "")
        }

    return {
        "ok": True,
        "rows_in": result["rows_in"],
        "rows_out": result["rows_out"],
        "output_key": output_key,
        "output_data": download_output(output_key)
    }
