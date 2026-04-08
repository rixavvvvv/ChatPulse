from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User
from app.services.user_service import get_user_by_email

settings = get_settings()


def hash_password(password: str) -> str:
    hashed_bytes = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed_bytes.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(
    user_id: int,
    workspace_id: int,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(
            minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "workspace_id": workspace_id,
        "exp": expire,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except InvalidTokenError as exc:
        raise ValueError("Invalid token") from exc


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    user = await get_user_by_email(session, email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
