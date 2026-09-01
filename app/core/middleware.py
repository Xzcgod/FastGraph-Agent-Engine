"""
自定义中间件模块 - 处理 HTTP 请求的横切关注点。

本模块包含两个中间件：

1. MetricsMiddleware：
   - 记录每个 HTTP 请求的耗时和状态码。
   - 将数据写入 Prometheus Counter 和 Histogram 指标。
   - 在 finally 块中执行，确保即使请求失败也能记录指标。

2. LoggingContextMiddleware：
   - 从 JWT Token 中提取 session_id 和 user_id。
   - 将提取的标识符绑定到 structlog 的上下文变量中。
   - 确保每个请求的日志都自动携带会话和用户信息。
   - 请求结束后清除上下文，防止跨请求数据泄露。

中间件执行顺序（在 main.py 中定义）：
    请求 → LoggingContextMiddleware → MetricsMiddleware → 路由处理器
"""

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
    """
    HTTP 请求指标采集中间件。

    对每个经过的 HTTP 请求，记录：
    - 请求总数（按 method、endpoint、status 分组）。
    - 请求耗时分布（按 method、endpoint 分组）。

    指标采集在 finally 块中进行，确保：
    - 正常响应的请求被记录。
    - 抛出异常的请求也被记录（状态码计为 500）。
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        拦截每个 HTTP 请求，采集指标后继续处理。

        Args:
            request: 当前 HTTP 请求对象。
            call_next: 调用下一个中间件或路由处理器的回调函数。

        Returns:
            Response: HTTP 响应对象。
        """
        # 记录请求开始时间（用于计算耗时）
        start_time = time.time()

        try:
            # 调用下游处理器（可能是下一个中间件，也可能是路由处理器）
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            # 如果处理器抛出未捕获的异常，状态码记为 500
            status_code = 500
            raise  # 重新抛出异常，让 FastAPI 的异常处理器处理
        finally:
            # 计算请求耗时（秒）
            duration = time.time() - start_time

            # 请求总数 +1（按 method、endpoint、status 标签分类）
            http_requests_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status=status_code
            ).inc()

            # 记录请求耗时观测值（直方图按分桶自动统计分布）
            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(duration)

        return response


class LoggingContextMiddleware(BaseHTTPMiddleware):
    """
    日志上下文中件间。

    从请求的 JWT Token 中提取会话和用户信息，绑定到 structlog 上下文，
    使得该请求的所有后续日志自动包含 session_id 和 user_id 字段。

    工作流程：
    1. 请求到达 → 清除上一个请求的上下文（防止污染）。
    2. 从 Authorization 头中提取 Bearer Token。
    3. 解码 JWT，获取 session_id（存在 sub 字段中）。
    4. 将 session_id 绑定到 structlog 上下文。
    5. 请求处理后 → 检查 request.state 中是否有 user_id（由认证依赖设置）。
    6. 最终清除上下文（无论成功或失败）。
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        拦截每个 HTTP 请求，提取认证信息并绑定到日志上下文。

        Args:
            request: 当前 HTTP 请求对象。
            call_next: 调用下一个中间件或路由处理器的回调函数。

        Returns:
            Response: HTTP 响应对象。
        """
        try:
            # 步骤 1: 清除之前请求的上下文
            # 这很重要——每个请求应该有独立的日志上下文
            clear_context()

            # 步骤 2: 从请求头中提取 Bearer Token
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

                try:
                    # 步骤 3: 解码 JWT Token
                    payload = jwt.decode(
                        token,
                        settings.JWT_SECRET_KEY,
                        algorithms=[settings.JWT_ALGORITHM]
                    )
                    # 步骤 4: 提取 session_id（JWT 的 sub 字段）
                    session_id = payload.get("sub")

                    if session_id:
                        # 将会话 ID 绑定到日志上下文
                        # 之后该请求的所有 structlog 日志都会自动包含 session_id
                        bind_context(session_id=session_id)

                except JWTError:
                    # Token 无效或过期——不在此处拒绝请求
                    # 原因：这个中间件的职责是日志上下文，而不是认证
                    # 认证失败应由 get_current_user 依赖项处理
                    pass

            # 步骤 5: 调用下游处理器（包括认证依赖项，会设置 request.state.user_id）
            response = await call_next(request)

            # 步骤 6: 请求处理后，检查是否有 user_id（由 get_current_user 依赖设置）
            if hasattr(request.state, "user_id"):
                bind_context(user_id=request.state.user_id)

            return response

        finally:
            # 步骤 7：无论请求成功或失败，清除上下文
            # 使用 finally 确保即使出现异常也不会泄露到下一个请求
            clear_context()
