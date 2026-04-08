import base64
import hashlib
import secrets

from app.core.config import get_settings

settings = get_settings()

_NONCE_BYTES = 16


def _build_keystream(secret: str, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0

    while len(output) < length:
        block = hashlib.sha256(
            secret.encode("utf-8") + nonce + counter.to_bytes(4, "big")
        ).digest()
        output.extend(block)
        counter += 1

    return bytes(output[:length])


def encrypt_secret(plaintext: str) -> str:
    data = plaintext.encode("utf-8")
    nonce = secrets.token_bytes(_NONCE_BYTES)
    keystream = _build_keystream(
        settings.meta_credentials_encryption_key, nonce, len(data))
    ciphertext = bytes(b ^ k for b, k in zip(data, keystream, strict=True))
    payload = nonce + ciphertext
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    payload = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
    if len(payload) < _NONCE_BYTES:
        raise ValueError("Invalid encrypted secret payload")

    nonce = payload[:_NONCE_BYTES]
    encrypted_data = payload[_NONCE_BYTES:]
    keystream = _build_keystream(
        settings.meta_credentials_encryption_key,
        nonce,
        len(encrypted_data),
    )
    plaintext = bytes(b ^ k for b, k in zip(
        encrypted_data, keystream, strict=True))
    return plaintext.decode("utf-8")
