import io
import json
import boto3
import traceback
import pandas as pd
import numpy as np
from functools import lru_cache

BUCKET_NAME = "makelele-pipeline-sandbox"

# Get the s3 client and caches the response
@lru_cache
def get_s3():
    return boto3.client("s3")

def lambda_handler(event, context):
    """Runs the sandbox code"""
    try:
        # Getting the object
        body = get_s3().get_object(Bucket = BUCKET_NAME, Key = event["input_key"])["Body"].read()
        data = pd.read_csv(io.BytesIO(body), dtype = str, keep_default_na = False)

        # Run the generated code which must be using def transform(data)
        scope = {"np": np, "pd": pd}
        exec(event["code"], scope)
        if "transform" not in scope:
            return {
                "ok": False,
                "error": "NameError: The code must have transform",
                "traceback": ""
            }

        output = scope["transform"](data.copy())
        if not isinstance(output, pd.DataFrame):
            return {
                "ok": False,
                "error": f"TypeError: transform returned {type(output).__name__}, expected DataFrame",
                "traceback": ""
            }

        # Convert the DataFrame into CSV
        buffer = io.StringIO()
        output.to_csv(buffer, index = False)
        get_s3().put_object(
            Bucket = BUCKET_NAME,
            Key = event["output_key"],
            Body = buffer.getvalue(),
            ContentType = "text/csv"
        )

        return {
            "ok": True,
            "rows_in": len(data),
            "rows_out": len(output)
        }

    except Exception as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc()[-2000:]
        }
