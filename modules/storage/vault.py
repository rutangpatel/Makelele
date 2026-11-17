from core.config import setting
from modules.security.encryption import encrypt_bytes, decrypt_bytes
from modules.aws.s3 import get_s3_client
from functools import lru_cache

@lru_cache
def s3():
    return get_s3_client()

def upload_encrypted(local_path: str, key: str):
    """Upload the encrypted file in S3 bucket"""
    with open(local_path, "rb") as file:
        data = file.read()

    encrypted_bytes = encrypt_bytes(data)

    s3().put_object(
        Bucket = setting.BUCKET_NAME,
        Key = key,
        Body = encrypted_bytes
    )

def download_decrypted(key: str, local_path: str):
    """Download file from S3 bucket and decrypt the file"""
    data = s3().get_object(
        Bucket = setting.BUCKET_NAME,
        Key = key
    )["Body"].read()

    decrypted_data = decrypt_bytes(data)

    with open(local_path, "wb") as file:
        file.write(decrypted_data)

if __name__ == "__main__":
    upload_encrypted("C:/Users/HP/Downloads/Rutang_s_Resume_Machine_Learning (1).pdf", "resume.pdf.enc")
    download_decrypted("resume.pdf.enc", "resume.pdf")
