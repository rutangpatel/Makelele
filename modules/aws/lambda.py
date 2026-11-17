import boto3
from core.config import setting

def get_lambda():
    lambda_client = boto3.client(
        "lambda",
        aws_access_key_id = setting.AWS_ACCESS_KEY_ID,
        aws_secret_access_key = setting.AWS_SECRET_ACCESS_KEY,
        region_name = setting.AWS_REGION_NAME
    )

    return lambda_client
