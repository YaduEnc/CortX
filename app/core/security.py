import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_secret(secret: str) -> str:
    return pwd_context.hash(secret)


def verify_secret(secret: str, secret_hash: str) -> bool:
    return pwd_context.verify(secret, secret_hash)


def _create_access_token(subject: str, token_type: str) -> str:
    settings = get_settings()
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expires_minutes)
    payload = {"sub": subject, "typ": token_type, "exp": expire_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_device_access_token(device_id: str) -> str:
    return _create_access_token(device_id, "device")


def create_app_access_token(user_id: str) -> str:
    return _create_access_token(user_id, "app")


def create_access_token(device_id: str) -> str:
    return create_device_access_token(device_id)


def decode_token_subject(token: str, expected_type: str) -> str | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

    token_type = payload.get("typ")
    if token_type is None and expected_type == "device":
        token_type = "device"
    if token_type != expected_type:
        return None

    return payload.get("sub")


def decode_access_token(token: str) -> str | None:
    return decode_token_subject(token, "device")


def hash_pair_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_pair_token(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_pair_token(token), token_hash)
