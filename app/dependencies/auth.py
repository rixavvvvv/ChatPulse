from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.models.user import User
from app.services.auth_service import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    session: AsyncSession = Depends(get_db_session),
    token: str = Depends(oauth2_scheme),
) -> User:
    unauthorized_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        user_id = int(subject)
    except (TypeError, ValueError):
        raise unauthorized_error

    user = await session.get(User, user_id)
    if not user:
        raise unauthorized_error

    return user
