from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretDecryptionError(Exception):
    """Raised when a stored ciphertext cannot be decrypted with the current key."""


def _fernet() -> Fernet:
    return Fernet(get_settings().fernet_key.get_secret_value().encode())


def encrypt(plaintext: str) -> bytes:
    if not plaintext:
        raise ValueError("Refusing to encrypt an empty string.")
    return _fernet().encrypt(plaintext.encode())


def decrypt(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(ciphertext).decode()
    except InvalidToken as exc:
        raise SecretDecryptionError("Fernet key does not match stored ciphertext.") from exc
