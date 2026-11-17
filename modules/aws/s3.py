import boto3
from core.config import setting

def get_s3_client():
    s3_client = boto3.client(
        "s3",
        region_name = setting.AWS_REGION_NAME
    )

    return s3_client
