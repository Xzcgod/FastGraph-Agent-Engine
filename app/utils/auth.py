"""This file contains the authentication utilities for the application."""

import re
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import (
    JWTError,
    jwt,
)

from app.core.config import settings
from app.core.logging import logger
from app.models.user import User
from app.schemas.auth import Token
from app.services.database import database_service
from app.utils.sanitization import sanitize_string

security = HTTPBearer()


def create_access_token(thread_id: str, expires_delta: Optional[timedelta] = None) -> Token:
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=settings.JWT_ACCESS_TOKEN_EXPIRE_DAYS)

    to_encode = {
        "sub": str(thread_id),
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": sanitize_string(f"{thread_id}-{datetime.now(UTC).timestamp()}"),
    }

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return Token(access_token=encoded_jwt, expires_at=expire)


def verify_token(token: str) -> Optional[str]:
    if not token or not isinstance(token, str):
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        thread_id: str = payload.get("sub")
        return thread_id
    except JWTError as e:
        logger.warning("token_validation_failed", error=str(e))
        return None


async def verify_session_access(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    token = credentials.credentials
    session_id = verify_token(token)

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return session_id


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    token = credentials.credentials
    subject = verify_token(token)

    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. 尝试作为 User ID 解析
    if subject.isdigit():
        user = await database_service.get_user_by_id(int(subject))
        if user:
            return user

    # 2. 尝试作为 Session ID 解析
    try:
        # ✅ 这里调用刚才修复的 get_session 方法
        session = await database_service.get_session(subject)
        if session:
            user = await database_service.get_user_by_id(session.user_id)
            if user:
                return user
            else:
                logger.error("session_found_but_user_missing", session_id=subject, user_id=session.user_id)
        else:
            # 只有在明确找不到 Session 时才打印，防止是 UserID 格式错误导致的误报
            logger.warning("session_not_found_in_db", session_id=subject)

    except Exception as e:
        logger.error("auth_db_lookup_failed", error=str(e))

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User not found",
        headers={"WWW-Authenticate": "Bearer"},
    )