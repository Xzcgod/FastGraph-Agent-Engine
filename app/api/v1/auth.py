"""认证相关的 API 路由配置。
"""

import uuid
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm

from app.core.logging import logger
from app.models.user import User
from app.schemas.auth import (
    SessionResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services.database import database_service
from app.utils.auth import (
    create_access_token,
    get_current_user,  # ✅ 直接导入修复好的依赖项
)
from app.utils.sanitization import sanitize_string

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate):
    """注册新用户"""
    # 1. 检查邮箱是否已存在
    existing_user = await database_service.get_user_by_email(user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # 2. 创建用户对象（密码哈希在 User 模型逻辑或 Service 中处理，这里假设 UserCreate 传入明文）
    # 注意：UserCreate schema 通常包含 password。
    # 我们需要在存入数据库前 hash 密码。
    hashed_password = User.hash_password(user_in.password)

    new_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
    )

    # 3. 保存到数据库
    user = await database_service.create_user(new_user)

    # 4. 生成 Token
    token = create_access_token(thread_id=str(user.id))

    return UserResponse(
        id=user.id,
        email=user.email,
        token=token,
    )


@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """用户登录"""
    # 1. 查找用户
    user = await database_service.get_user_by_email(form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. 验证密码
    if not user.verify_password(form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. 生成 Token
    access_token = create_access_token(thread_id=str(user.id))

    return TokenResponse(
        access_token=access_token.access_token,
        token_type="bearer",
        expires_at=access_token.expires_at
    )


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    name: str = "New Chat",
    user: User = Depends(get_current_user),
):
    """创建新的聊天会话"""
    try:
        session_id = str(uuid.uuid4())
        sanitized_name = sanitize_string(name) or "New Chat"

        # 创建会话
        session = await database_service.create_session(
            user_id=user.id,
            name=sanitized_name,
            session_id=session_id
        )

        # 为会话生成专属 Token
        token = create_access_token(thread_id=session_id)

        return SessionResponse(
            session_id=session.id,
            name=session.name,
            token=token,
        )
    except Exception as e:
        logger.error("create_session_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to create session")


@router.get("/sessions", response_model=List[SessionResponse])
async def get_user_sessions(user: User = Depends(get_current_user)):
    """获取当前用户的所有会话"""
    try:
        sessions = await database_service.get_user_sessions(user.id)
        return [
            SessionResponse(
                session_id=s.id,
                name=s.name,
                token=create_access_token(s.id), # 重新签发 token 或返回 null，视需求而定，这里返回可用 token
            )
            for s in sessions
        ]
    except Exception as e:
        logger.error("get_sessions_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve sessions")


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
):
    """删除会话"""
    # 验证会话归属权
    session = await database_service.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    await database_service.delete_session(session_id)