import boto3
from botocore.config import Config
from core.config import setting

def get_lambda():
    lambda_client = boto3.client(
        "lambda",
        region_name = setting.AWS_REGION_NAME,
        config = Config(
            read_timeout = 90,
            connect_timeout = 10,
            retries = {"max_attempts": 0}
        )
    )

    return lambda_client
