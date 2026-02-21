"""自定义中间件，用于处理指标记录和日志上下文等横切关注点"""

import time
from typing import Callable

from fastapi import Request
from jose import (
    JWTError,
    jwt,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import (
    bind_context,
    clear_context,
)
from app.core.metrics import (
    db_connections,
    http_request_duration_seconds,
    http_requests_total,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """中间件：记录每个 HTTP 请求的指标。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track metrics for each request.
        """
        start_time = time.time()# 记录请求开始时间

        try:
            response = await call_next(request)# 调用下一个中间件或路由处理
            status_code = response.status_code
        except Exception:
            status_code = 500# 如果发生未捕获异常，状态码设为 500
            raise # 重新抛出异常，让上层处理
        finally:
            duration = time.time() - start_time# 计算请求耗时

            # 记录请求总数计数器（增加1），带上 method、endpoint、status 标签
            http_requests_total.labels(method=request.method, endpoint=request.url.path, status=status_code).inc()
            # 记录请求耗时直方图观测值，带上 method、endpoint 标签
            http_request_duration_seconds.labels(method=request.method, endpoint=request.url.path).observe(duration)

        return response


class LoggingContextMiddleware(BaseHTTPMiddleware):
    """中间件：从 JWT 中提取用户 ID 和会话 ID，并将其绑定到日志上下文。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Extract user_id and session_id from authenticated requests and add to logging context.
        """
        try:
            # 清除之前请求留下的上下文（防止跨请求污染）
            clear_context()

            # 从请求头中获取 Authorization 信息
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

                try:
                    # 使用 JWT 解码 token，验证签名并获取 payload
                    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
                    session_id = payload.get("sub")# 假设会话 ID 存储在 sub 字段中

                    if session_id:
                        # 将会话 ID 绑定到日志上下文（后续所有日志都会包含 session_id 字段）
                        bind_context(session_id=session_id)

                        # 注意：user_id 可能在请求处理过程中由依赖项设置到 request.state 中
                        # 我们将在请求处理完成后检查并绑定 user_id

                except JWTError:
                    # token 无效，但不立即拒绝请求——让后续的认证依赖处理
                    pass

            # 调用下一个中间件/路由，处理实际请求
            response = await call_next(request)

            # 请求处理完成后，检查 request.state 中是否由认证依赖设置了 user_id
            if hasattr(request.state, "user_id"):
                bind_context(user_id=request.state.user_id)# 绑定用户 ID 到日志上下文

            return response

        finally:
            # 无论请求成功或失败，都要清除上下文，避免内存泄漏和跨请求影响
            clear_context()
