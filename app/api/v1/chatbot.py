"""
聊天机器人 API 路由模块。

本模块定义了与 LangGraph Agent 交互的 REST API 端点：
- POST /chat         : 普通对话（等待完整生成后返回）。
- POST /chat/stream   : 流式对话（Server-Sent Events 风格，逐 Token 返回）。
- GET  /history       : 获取指定会话的聊天记录。
- DELETE /history     : 清空指定会话的聊天记录。
- POST /chat/resume   : 恢复被中断的会话（如邮件审批后的继续执行）。

认证与授权：
    所有端点都需要有效的 JWT Token 和会话访问权限（通过 verify_session_access 依赖验证）。
"""

from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from fastapi.responses import StreamingResponse

from app.core.langgraph.graph import chatbot
from app.core.logging import logger
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    EmailApprovalRequest,
    Message,
)
from app.utils.auth import (
    get_current_user,
    verify_session_access,
)

router = APIRouter()


# ============================================================================
# 对话端点
# ============================================================================

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    session_id: str = Depends(verify_session_access),
    user: User = Depends(get_current_user),
):
    """
    普通对话接口 - 等待 AI 完整生成回复后返回。

    这是标准的请求-响应模式：
    - 前端发送完整的消息列表 + 功能开关配置。
    - 后端执行完整的 LangGraph 工作流（可能包含多轮工具调用）。
    - 等待所有处理完成后，一次性返回最终的 AI 回复。

    适用场景：
    - 不需要实时反馈的对话场景。
    - 简单的问答场景。
    - 调试和测试。

    Args:
        request: 聊天请求体，包含消息列表和功能开关。
        session_id: 会话 ID（由 verify_session_access 从 JWT 中提取并验证）。
        user: 当前认证用户（由 get_current_user 依赖注入）。

    Returns:
        ChatResponse: 包含 AI 回复消息列表的响应。

    Raises:
        HTTPException(500): LangGraph 执行过程中发生错误时抛出。
    """
    try:
        response_messages = await chatbot.get_response(
            session_id=session_id,
            messages=request.messages,
            features=request.features.model_dump() if request.features else {},
            user_id=str(user.id),
        )
        return ChatResponse(messages=response_messages)
    except Exception as e:
        logger.exception("chat_endpoint_error", error=str(e), session_id=session_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    session_id: str = Depends(verify_session_access),
    user: User = Depends(get_current_user),
):
    """
    流式对话接口 - 提供打字机效果的实时输出。

    使用 StreamingResponse 实现 Server-Sent Events 风格的流式传输：
    - AI 每生成一段文本，立即通过流发送给前端。
    - 前端可以实时渲染，提供类似 ChatGPT 的打字机效果。
    - 工具调用过程中会发送特殊标记（如 "正在调用工具: xxx"）。

    流式传输的内容包括：
    - AI 文本回复（逐段输出）。
    - 工具调用进度提示（带特殊格式，前端可解析展示）。
    - 中断信号（邮件审批等需要人工介入时）。

    Args:
        request: 聊天请求体，包含消息列表和功能开关。
        session_id: 会话 ID（由 verify_session_access 从 JWT 中提取并验证）。
        user: 当前认证用户。

    Returns:
        StreamingResponse: 流式响应（text/plain 媒体类型）。
    """
    async def event_generator():
        """
        异步生成器 - 逐块产出 AI 回复内容。

        直接使用 async for 消费 Chatbot.astream_response() 的异步生成器，
        每个 yield 出的字符串块直接转发给前端。
        """
        try:
            # 调用 Graph 的流式方法，逐块获取 AI 回复
            async for chunk in chatbot.astream_response(
                session_id=session_id,
                messages=request.messages,
                features=request.features.model_dump() if request.features else {},
                user_id=str(user.id),
            ):
                # 直接转发内容块给前端
                # 前端可以按行读取或使用 SSE 解析
                yield chunk
        except Exception as e:
            logger.exception("chat_stream_error", error=str(e), session_id=session_id)
            # 即使出错也通过流通知前端
            yield f"\n[Error: {str(e)}]"

    return StreamingResponse(
        event_generator(),
        media_type="text/plain"  # 使用 text/plain 保持简单通用
    )


# ============================================================================
# 对话历史管理
# ============================================================================

@router.get("/history", response_model=List[Message])
async def get_history(session_id: str = Depends(verify_session_access)):
    """
    获取指定会话的聊天历史记录。

    从 LangGraph 的检查点（Checkpoint）中读取持久化的对话状态，
    返回完整的消息列表。

    Args:
        session_id: 会话 ID。

    Returns:
        List[Message]: 对话消息列表。
    """
    return await chatbot.get_chat_history(session_id)


@router.delete("/history")
async def clear_history(session_id: str = Depends(verify_session_access)):
    """
    清空指定会话的聊天历史记录。

    删除 LangGraph 在 PostgreSQL 中保存的检查点数据：
    - checkpoints 表：对话状态快照。
    - checkpoint_blobs 表：二进制大数据。
    - checkpoint_writes 表：待处理的写操作。

    注意：此操作不可逆，清空后无法恢复对话历史。

    Args:
        session_id: 会话 ID。

    Returns:
        dict: 包含成功消息的响应。
    """
    await chatbot.clear_chat_history(session_id)
    return {"message": "History cleared"}


# ============================================================================
# 会话恢复（Human-in-the-loop）
# ============================================================================

@router.post("/chat/resume")
async def resume_chat(
    request: EmailApprovalRequest,
    user: User = Depends(get_current_user),
):
    """
    恢复被中断的会话执行。

    使用场景：
        当 LangGraph 执行到需要人工审批的步骤（如发送邮件）时，
        图会暂停（interrupt），等待用户确认。前端展示审批卡片，
        用户点击批准/拒绝后，调用此接口恢复执行。

    工作流程：
        1. Agent 调用 prepare_email 工具 → 触发 interrupt 暂停。
        2. 前端检测到暂停信号 → 展示审批卡片。
        3. 用户点击批准/拒绝 → 前端调用 /chatbot/resume。
        4. 后端向 LangGraph 发送 Command(resume="approved"/"rejected")。
        5. Agent 继续执行（发送邮件或取消）。

    Args:
        request: 包含 session_id 和 approved 字段的请求体。
        user: 当前认证用户。

    Returns:
        dict: 包含执行结果的响应消息。
    """
    result = await chatbot.resume_graph(request.session_id, request.approved)
    return {"message": result}

