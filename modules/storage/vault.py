from core.config import setting
from modules.security.encryption import encrypt_bytes, decrypt_bytes
from modules.aws.s3 import get_s3_client
from functools import lru_cache

PREFIX = "Vault"

@lru_cache
def s3():
    return get_s3_client()

def upload_encrypted(data: bytes, job_id: str):
    """Upload the encrypted file in S3 bucket"""
    s3().put_object(
        Bucket = setting.BUCKET_NAME,
        Key = f"{PREFIX}/{job_id}/original.csv.enc",
        Body = encrypt_bytes(data)
    )

def download_decrypted(key: str):
    """Download file from S3 bucket and decrypt the file"""
    data = s3().get_object(
        Bucket = setting.BUCKET_NAME,
        Key = key
    )["Body"].read()

    return decrypt_bytes(data)
