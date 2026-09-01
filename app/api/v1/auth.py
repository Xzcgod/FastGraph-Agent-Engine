"""
认证相关的 API 路由模块。

本模块定义了用户认证和会话管理的 REST API 端点：
- POST /register  : 用户注册（创建账号并返回 Token）。
- POST /login     : 用户登录（验证邮箱密码并返回 Token）。
- POST /sessions  : 创建新的聊天会话（需要认证）。
- GET  /sessions  : 获取当前用户的所有会话列表（需要认证）。
- DELETE /sessions/{session_id} : 删除指定会话（需要认证 + 所有权验证）。

安全设计：
1. 密码使用 bcrypt 哈希存储，不保存明文。
2. 注册和登录返回 JWT Token，包含 user_id 或 session_id。
3. 会话操作基于 Token 认证，每个操作都验证用户身份和资源归属。
4. 会话名称经过净化处理（sanitize_string），防止 XSS/注入攻击。
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
    get_current_user,  # 直接导入修复好的认证依赖项
)
from app.utils.sanitization import sanitize_string

# 创建路由器实例
# 该路由器在 api.py 中被挂载到 /auth 路径下
router = APIRouter()


# ============================================================================
# 用户注册与登录
# ============================================================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate):
    """
    注册新用户。

    处理流程：
        1. 检查邮箱是否已被注册（重复注册返回 400 错误）。
        2. 使用 bcrypt 对密码进行哈希处理（不存储明文密码）。
        3. 将用户信息存入数据库。
        4. 为用户生成 JWT 访问令牌。
        5. 返回用户信息 + 令牌。

    Args:
        user_in: 包含 email 和 password 的注册请求体。
                 password 使用 SecretStr 包装，防止在日志中泄露。

    Returns:
        UserResponse: 包含用户 ID、邮箱和认证令牌的响应（HTTP 201）。

    Raises:
        HTTPException(400): 当邮箱已被注册时抛出。
    """
    # 步骤 1: 检查邮箱是否已存在
    existing_user = await database_service.get_user_by_email(user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # 步骤 2: 对密码进行 bcrypt 哈希处理
    hashed_password = User.hash_password(user_in.password.get_secret_value())

    # 步骤 3: 创建用户对象
    new_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
    )

    # 步骤 4: 保存到数据库
    user = await database_service.create_user(new_user)

    # 步骤 5: 生成 JWT Token（使用用户 ID 作为 subject）
    token = create_access_token(thread_id=str(user.id))

    return UserResponse(
        id=user.id,
        email=user.email,
        token=token,
    )


@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    用户登录。

    使用 OAuth2 密码授权流程（OAuth2PasswordRequestForm）接收凭据：
    - username 字段实际承载的是用户邮箱。
    - password 字段承载明文密码。

    处理流程：
        1. 根据邮箱查找用户（不存在 → 401）。
        2. 验证密码（不匹配 → 401）。
        3. 生成并返回 JWT 访问令牌。

    安全注意事项：
        - 登录失败时不区分"邮箱不存在"和"密码错误"，
          统一返回 "Incorrect email or password"，防止用户枚举攻击。
        - 密码验证使用 bcrypt.checkpw，具有恒定时间比较特性。

    Args:
        form_data: OAuth2 密码表单数据。

    Returns:
        TokenResponse: 包含 access_token、token_type 和 expires_at 的响应。

    Raises:
        HTTPException(401): 邮箱不存在或密码错误时抛出。
    """
    # 步骤 1: 查找用户（注意 OAuth2 表单的 username 字段对应邮箱）
    user = await database_service.get_user_by_email(form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 步骤 2: 验证密码
    if not user.verify_password(form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 步骤 3: 生成 JWT Token
    access_token = create_access_token(thread_id=str(user.id))

    return TokenResponse(
        access_token=access_token.access_token,
        token_type="bearer",
        expires_at=access_token.expires_at
    )


# ============================================================================
# 会话管理
# ============================================================================

@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    name: str = "New Chat",
    user: User = Depends(get_current_user),
):
    """
    创建新的聊天会话。

    每个会话会自动关联一个 LangGraph Thread（用于持久化对话状态），
    并生成一个专属的 JWT Token（用于后续消息请求的身份验证）。

    Args:
        name: 会话名称，默认为 "New Chat"（会经过净化处理）。
        user: 当前认证用户（由 get_current_user 依赖注入）。

    Returns:
        SessionResponse: 包含 session_id、name 和专属 Token 的响应。

    Raises:
        HTTPException(500): 创建会话过程中发生数据库错误时抛出。
    """
    try:
        # 生成唯一的会话 ID
        session_id = str(uuid.uuid4())
        # 净化会话名称（移除 XSS/注入风险字符），空名称回退为默认值
        sanitized_name = sanitize_string(name) or "New Chat"

        # 创建会话（同时创建 LangGraph Thread）
        session = await database_service.create_session(
            user_id=user.id,
            name=sanitized_name,
            session_id=session_id
        )

        # 为会话生成专属的 JWT Token
        # 后续发送消息时使用此 Token，可同时验证身份和确定会话上下文
        token = create_access_token(thread_id=session_id)

        return SessionResponse(
            session_id=session.id,
            name=session.name,
            token=token,
        )
    except Exception as e:
        logger.exception("create_session_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to create session")


@router.get("/sessions", response_model=List[SessionResponse])
async def get_user_sessions(user: User = Depends(get_current_user)):
    """
    获取当前用户的所有聊天会话列表。

    会话按创建时间倒序排列（最新的在最前面），
    每个会话附带一个重新签发的 JWT Token。

    Args:
        user: 当前认证用户（由 get_current_user 依赖注入）。

    Returns:
        List[SessionResponse]: 会话列表。

    Raises:
        HTTPException(500): 数据库查询失败时抛出。
    """
    try:
        sessions = await database_service.get_user_sessions(user.id)
        return [
            SessionResponse(
                session_id=s.id,
                name=s.name,
                # 重新签发 Token（确保 Token 在有效期内）
                token=create_access_token(s.id),
            )
            for s in sessions
        ]
    except Exception as e:
        logger.exception("get_sessions_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve sessions")


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
):
    """
    删除指定的聊天会话。

    安全验证：
    1. 验证 Token 有效（由 get_current_user 确保）。
    2. 验证会话属于当前用户（防止越权删除他人会话）。

    Args:
        session_id: 要删除的会话 ID。
        user: 当前认证用户。

    Raises:
        HTTPException(404): 会话不存在或不属于当前用户时抛出。

    Returns:
        None: 成功删除返回 HTTP 204 No Content（无响应体）。
    """
    # 验证会话存在且属于当前用户
    session = await database_service.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    # 执行删除
    await database_service.delete_session(session_id)
