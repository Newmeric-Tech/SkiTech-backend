import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

IV_LENGTH = 12

def get_encryption_key() -> bytes:
    key_env = settings.CREDENTIALS_ENCRYPTION_KEY or os.getenv("CREDENTIALS_ENCRYPTION_KEY")
    if not key_env:
        if settings.is_production:
            raise RuntimeError(
                "CREDENTIALS_ENCRYPTION_KEY must be set in production; "
                "it encrypts stored channel-manager provider credentials."
            )
        # Fallback to keep local dev running without extra setup
        return hashlib.sha256(b"dev-fallback-key-antigravity").digest()

    # Check if 64-char hex string
    if len(key_env) == 64 and all(c in "0123456789abcdefABCDEF" for c in key_env):
        return bytes.fromhex(key_env)
        
    return hashlib.sha256(key_env.encode("utf-8")).digest()


def encrypt(text: str) -> str:
    key = get_encryption_key()
    data = text.encode("utf-8")
    iv = os.urandom(IV_LENGTH)
    
    aesgcm = AESGCM(key)
    # cryptography encrypt returns ciphertext + 16-byte auth tag
    encrypted_data = aesgcm.encrypt(iv, data, None)
    
    ciphertext = encrypted_data[:-16]
    tag = encrypted_data[-16:]
    
    iv_base64 = base64.b64encode(iv).decode("utf-8")
    ciphertext_base64 = base64.b64encode(ciphertext).decode("utf-8")
    tag_base64 = base64.b64encode(tag).decode("utf-8")
    
    return f"{iv_base64}:{ciphertext_base64}:{tag_base64}"


def decrypt(encrypted_text: str) -> str:
    key = get_encryption_key()
    parts = encrypted_text.split(":")
    
    if len(parts) < 2:
        raise ValueError("Invalid encrypted text format. Must be iv:ciphertext[:tag]")
        
    iv_base64 = parts[0]
    ciphertext_base64 = parts[1]
    
    iv = base64.b64decode(iv_base64)
    ciphertext = base64.b64decode(ciphertext_base64)
    
    aesgcm = AESGCM(key)
    
    if len(parts) >= 3:
        tag_base64 = parts[2]
        tag = base64.b64decode(tag_base64)
        # AESGCM decrypt expects ciphertext concatenated with the tag
        payload = ciphertext + tag
    else:
        payload = ciphertext
        
    decrypted_data = aesgcm.decrypt(iv, payload, None)
    return decrypted_data.decode("utf-8")
