"""聊天相关的 Pydantic Schema 定义（完整版）。

FeatureFlags 含全部 5 个功能开关：
    web_search       - 联网搜索（Tavily）
    code_interpreter - Python 代码沙盒
    memory_tools     - 长期记忆工具（主动保存/检索）
    email_assistant  - 邮件助手（含 Human-in-the-loop 审批）
    knowledge_base   - RAG 知识库检索
"""

import re
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Message(BaseModel):
    """消息模型"""

    model_config = {"extra": "ignore"}

    role: Literal["user", "assistant", "system"] = Field(..., description="消息发送方的角色")
    content: str = Field(..., description="消息内容", min_length=1, max_length=3000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """验证消息内容安全性"""
        if re.search(r"<script.*?>.*?</script>", v, re.IGNORECASE | re.DOTALL):
            raise ValueError("Content contains potentially harmful script tags")
        if "\0" in v:
            raise ValueError("Content contains null bytes")
        return v


class FeatureFlags(BaseModel):
    """功能开关 - 前端通过此字段控制 Agent 的能力范围。

    设计原则：最小权限，按需激活。所有功能默认关闭。

    前端请求示例：
    {
        "messages": [...],
        "features": {
            "web_search": true,        // 开启联网搜索
            "code_interpreter": true,  // 开启代码沙盒
            "memory_tools": true,      // 开启记忆工具
            "email_assistant": true,   // 开启邮件助手
            "knowledge_base": true     // 开启知识库检索
        }
    }
    """

    model_config = {"extra": "ignore"}

    # 联网搜索（Tavily，无 Key 自动降级 DuckDuckGo）
    web_search: bool = Field(default=False, description="是否开启联网搜索能力")

    # Python 代码沙盒（PythonREPLTool）
    code_interpreter: bool = Field(default=False, description="是否开启 Python 代码执行能力")

    # 长期记忆工具（SaveMemory + SearchMemory，Agent 主动调用）
    memory_tools: bool = Field(default=False, description="是否开启长期记忆工具")

    # 邮件助手（PrepareEmail + SendEmail，含 Human-in-the-loop 审批）
    email_assistant: bool = Field(default=False, description="是否开启邮件发送能力（需人工审批）")

    # RAG 知识库检索（混合检索 + Rerank）
    knowledge_base: bool = Field(default=False, description="是否开启知识库检索能力")


class ChatRequest(BaseModel):
    """聊天请求模型。

    features 字段控制 Agent 工具能力，不传则全部关闭（纯聊天模式）。
    """

    messages: List[Message] = Field(
        ...,
        description="对话消息列表",
        min_length=1,
    )
    features: Optional[FeatureFlags] = Field(
        default=None,
        description="功能特性开关，控制 Agent 可用工具范围。不传则使用默认（全部关闭）",
    )


class ChatResponse(BaseModel):
    """聊天响应模型"""

    messages: List[Message] = Field(..., description="对话消息列表")


class StreamResponse(BaseModel):
    """流式聊天响应模型"""

    content: str = Field(default="", description="当前流式块的内容")
    done: bool = Field(default=False, description="是否已完成流式输出")


class EmailApprovalRequest(BaseModel):
    """邮件审批请求模型 - 前端用户批准/拒绝发送邮件时提交。

    前端在收到 Human-in-the-loop 暂停信号后，
    调用 /chatbot/resume 接口传入此 Schema。
    """

    session_id: str = Field(..., description="会话 ID")
    approved: bool = Field(..., description="true=批准发送，false=拒绝发送")
    human_response: Optional[Dict] = Field(
        default=None,
        description="传给 LangGraph 的完整响应对象，不传时自动构建",
    )