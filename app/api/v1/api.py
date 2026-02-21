"""API v1 router configuration.

文件名：api.py
位置：app/api/v1/api.py
作用：API 路由的汇总中心。负责把认证、聊天等分散的功能把它们“打包”在一起。
"""

# APIRouter 是 FastAPI 提供的一个“迷你应用”。
# 它像一个插线板，可以插很多个具体的接口，最后再把这个插线板插到主墙座(main.py)上。
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chatbot import router as chatbot_router
from app.core.logging import logger

api_router = APIRouter()

# Include routers
# 动作：把“认证科”挂载进来。
# - router: 具体的办事处代码 (auth_router)
# - prefix="/auth": 意思是，凡是网址里带 "/auth" 的，都往这儿领。
#   例如：用户访问 /api/v1/auth/login -> 就会被指派给 auth_router 处理。
# - tags=["auth"]: 给文档贴个标签。在 Swagger 文档页面，所有认证接口会被归类在 "auth" 这一栏下面，整整齐齐。
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])


# 这是一个直接写在总监办公室门口的小窗口。
# 通常用来检查这个 v1 版本的 API 部门是不是还活着。
# 访问地址会是： /api/v1/health
@api_router.get("/health")
async def health_check():
    """Health check endpoint.

    Returns:
        dict: Health status information.
    """
    logger.info("health_check_called")
    return {"status": "healthy", "version": "1.0.0"}