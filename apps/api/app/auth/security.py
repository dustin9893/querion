from datetime import datetime, timedelta, timezone

# -- passlib + bcrypt >= 4.1 compatibility workaround ----------------------
# passlib's internal bug-detection sends a >72-byte password which newer
# bcrypt rejects.  Monkey-patching before CryptContext is created avoids it.
import passlib.utils

passlib.utils.MAX_PASSWORD_SIZE = 1024
# --------------------------------------------------------------------------

from jose import JWTError, jwt  # noqa: E402  (phải nạp sau bản vá passlib ở trên)
from passlib.context import CryptContext  # noqa: E402

from app.config import settings  # noqa: E402

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password[:72], hashed_password)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def create_access_token(user_id: str, role: str, **claims) -> str:
    """``claims`` are extra, non-sensitive facts about the session — e.g. the staff ``client``
    (portal | extension) that decides which assistants are listed and how runs are audited."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "exp": expire,
        **{k: v for k, v in claims.items() if v is not None},
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str, **claims) -> str:
    """The refresh token carries the same extra claims so a refreshed access token keeps them."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        **{k: v for k, v in claims.items() if v is not None},
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Decode and verify a JWT token. Returns payload dict or None."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None
