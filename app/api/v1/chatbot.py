"""API 路由定义：处理 HTTP 请求，验证参数，调用底层 Graph 逻辑。
"""

import os
import shutil
import json
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.langgraph.graph import chatbot
from app.core.langgraph.tools.rag_tool import ingest_file
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


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    session_id: str = Depends(verify_session_access),
    user: User = Depends(get_current_user),
):
    """普通对话接口（等待完全生成后返回）"""
    try:
        response_messages = await chatbot.get_response(
            session_id=session_id,
            messages=request.messages,
            features=request.features.model_dump() if request.features else {},
            user_id=str(user.id),
        )
        return ChatResponse(messages=response_messages)
    except Exception as e:
        logger.error("chat_endpoint_error", error=str(e), session_id=session_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    session_id: str = Depends(verify_session_access),
    user: User = Depends(get_current_user),
):
    """
    ✅ 流式对话接口 (Server-Sent Events 风格)
    前端可以通过读取流来获取打字机效果。
    """
    async def event_generator():
        try:
            # 调用 Graph 的流式方法
            async for chunk in chatbot.astream_response(
                session_id=session_id,
                messages=request.messages,
                features=request.features.model_dump() if request.features else {},
                user_id=str(user.id),
            ):
                # 包装为 SSE (Server-Sent Events) 格式或简单的行数据
                # 这里为了简单通用，直接发送内容块，前端按行读取即可
                # 如果需要严格的 SSE，可以使用 f"data: {json.dumps({'content': chunk})}\n\n"
                yield chunk
        except Exception as e:
            logger.error("chat_stream_error", error=str(e), session_id=session_id)
            yield f"\n[Error: {str(e)}]"

    return StreamingResponse(
        event_generator(),
        media_type="text/plain"  # 或者 "text/event-stream"
    )


@router.get("/history", response_model=List[Message])
async def get_history(session_id: str = Depends(verify_session_access)):
    return await chatbot.get_chat_history(session_id)


@router.delete("/history")
async def clear_history(session_id: str = Depends(verify_session_access)):
    await chatbot.clear_chat_history(session_id)
    return {"message": "History cleared"}


@router.post("/chat/resume")
async def resume_chat(
    request: EmailApprovalRequest,
    user: User = Depends(get_current_user),
):
    """恢复被中断（如邮件审批）的会话"""
    result = await chatbot.resume_graph(request.session_id, request.approved)
    return {"message": result}


@router.post("/rag/upload")
async def upload_document(
    file: UploadFile = File(...),
    session_id: str = Depends(verify_session_access),
):
    """上传并解析文档"""
    upload_dir = settings.RAG_UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        count = await ingest_file(file_path, file.filename)
        return {"message": f"成功上传并解析 {count} 个片段", "filename": file.filename}
    except ImportError:
        logger.error("rag_missing_dependency")
        raise HTTPException(status_code=500, detail="服务器缺少 PDF 解析库 (fitz)")
    except Exception as e:
        logger.error("rag_upload_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))