import os
import json
import base64
from modules.aws.secrets_manager import get_secret_manager
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# Cache for the secrets manager
client = get_secret_manager()
cache = SecretCache(
    client = client,
    config = SecretCacheConfig(secret_refresh_interval = 3600)
)

def get_secret_key():
    """Gets the key and then cache for an hour"""
    key_name = "makelele-secrets"
    secret_key = cache.get_secret_string(key_name)
    return base64.b64decode(json.loads(secret_key)["file_encryption_key"])

def encrypt_bytes(data: bytes):
    """Encryption of the file"""
    nonce = os.urandom(12)
    encrypted_bytes = AESGCM(get_secret_key()).encrypt(nonce, data, None)
    return nonce + encrypted_bytes

def decrypt_bytes(data: bytes):
    """Decryption of the file"""
    decrypted_bytes = AESGCM(get_secret_key()).decrypt(data[:12], data[12:], None)
    return decrypted_bytes
