"""Fernet-based encryption/decryption for storing API keys in DB."""

from cryptography.fernet import Fernet

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        from app.config import settings
        if not settings.ENCRYPTION_KEY:
            raise RuntimeError(
                "ENCRYPTION_KEY env var is required for API key encryption. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        _fernet = Fernet(settings.ENCRYPTION_KEY.encode())
    return _fernet


def encrypt_key(plaintext: str) -> str:
    """Encrypt an API key → base64 ciphertext string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    """Decrypt a stored ciphertext → plaintext API key."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def mask_key(plaintext: str) -> str:
    """Mask API key for display: sk-...xxxx"""
    if len(plaintext) <= 8:
        return "****"
    return f"{plaintext[:3]}...{plaintext[-4:]}"
