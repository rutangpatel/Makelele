import os
import base64
from core.config import get_secret
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def get_secret_key():
    """AES key from the cached app secret"""
    return base64.b64decode(get_secret("file_encryption_key"))

def encrypt_bytes(data: bytes):
    """Encryption of the file"""
    nonce = os.urandom(12)
    encrypted_bytes = AESGCM(get_secret_key()).encrypt(nonce, data, None)
    return nonce + encrypted_bytes

def decrypt_bytes(data: bytes):
    """Decryption of the file"""
    decrypted_bytes = AESGCM(get_secret_key()).decrypt(data[:12], data[12:], None)
    return decrypted_bytes
