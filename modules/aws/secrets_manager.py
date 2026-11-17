import boto3
from core.config import setting

def get_secret_manager():
    secret_client = boto3.client(
        "secretsmanager",
        region_name = setting.AWS_REGION_NAME
    )

    return secret_client

print(get_secret_manager())
