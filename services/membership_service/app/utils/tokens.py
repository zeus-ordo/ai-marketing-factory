import secrets
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from app.config import settings


def generate_secure_token() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(payload: dict, expires_delta: int | None = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(seconds=expires_delta or settings.JWT_ACCESS_EXPIRY)
    data = {
        **payload,
        "exp": exp,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(data, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


def hash_token(token: str) -> str:
    return bcrypt.hashpw(token.encode(), bcrypt.gensalt(rounds=10)).decode()


def verify_token(token: str, token_hash: str) -> bool:
    return bcrypt.checkpw(token.encode(), token_hash.encode())
