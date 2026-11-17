import boto3
from core.config import setting

def get_lambda():
    lambda_client = boto3.client(
        "lambda",
        region_name = setting.AWS_REGION_NAME
    )

    return lambda_client
