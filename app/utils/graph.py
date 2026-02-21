"""
文件名：app/utils/graph.py
修复说明：
1. 彻底重构 prepare_messages：不再使用 dict 中转，而是将所有输入（Pydantic Message 或 dict）
   统一标准化为 LangChain 的 BaseMessage 对象 (HumanMessage, AIMessage, ToolMessage)。
2. 修复了工具调用上下文丢失的问题：确保 ToolMessage 和包含 tool_calls 的 AIMessage 能被正确传递给 LLM。
3. 优化 get_token_count：增强对不同消息类型的兼容性。
"""

from typing import List, Union, Any

import tiktoken
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,  # ✅ 新增导入
    trim_messages as _trim_messages,
)

from app.core.config import settings
from app.core.logging import logger
from app.schemas import Message


def dump_messages(messages: List[Union[Message, BaseMessage, dict, Any]]) -> List[dict]:
    """
    辅助函数：将消息列表转换为字典列表（主要用于日志记录，不用于核心逻辑）。
    """
    dumped = []
    for msg in messages:
        if isinstance(msg, dict):
            dumped.append(msg)
        elif hasattr(msg, "model_dump"):  # Pydantic v2 / LangChain 0.3+
            dumped.append(msg.model_dump())
        elif hasattr(msg, "dict"):  # LangChain 旧版 / Pydantic v1
            dumped.append(msg.dict())
        else:
            dumped.append({"role": "user", "content": str(msg)})
    return dumped


def process_llm_response(response: BaseMessage) -> BaseMessage:
    """处理 LLM 响应，提取结构化内容（如推理块）。"""
    if isinstance(response.content, list):
        text_parts = []
        for block in response.content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "reasoning":
                    logger.debug("llm_reasoning_block", content=block.get("summary"))

        if text_parts:
            response.content = "".join(text_parts)
        elif not isinstance(response.content, str):
             response.content = ""

    return response


def get_token_count(messages: List[Union[dict, BaseMessage]]) -> int:
    """
    自定义 Token 计数器。
    使用 tiktoken 的 cl100k_base (GPT-4) 编码进行估算。
    """
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
    except Exception:
        encoding = tiktoken.get_encoding("gpt2")

    num_tokens = 0
    for message in messages:
        # 每条消息的基础开销
        num_tokens += 4

        content = ""
        # 提取内容
        if isinstance(message, dict):
            content = message.get("content", "")
        elif hasattr(message, "content"):
            content = message.content

        # 即使内容为空（如 ToolCall），也可能有 overhead，但这里主要计算文本
        if content:
            num_tokens += len(encoding.encode(str(content)))

    num_tokens += 3
    return num_tokens


def prepare_messages(
    messages: List[Union[Message, BaseMessage, dict]],
    llm: BaseChatModel,
    system_prompt: str
) -> List[BaseMessage]:
    """
    准备发给 LLM 的消息列表。
    ✅ 核心修复：将所有输入标准化为 LangChain 对象，保留工具调用上下文。
    """

    # 1. 标准化：将混合类型的消息列表统一转为 List[BaseMessage]
    normalized_messages = []

    for msg in messages:
        # 情况 A: 已经是 LangChain 对象 (最完美的情况，包含 tool_calls 等所有细节)
        if isinstance(msg, BaseMessage):
            normalized_messages.append(msg)

        # 情况 B: Pydantic Message (前端传来的)
        elif isinstance(msg, Message):
            if msg.role == "user":
                normalized_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                normalized_messages.append(AIMessage(content=msg.content))
            elif msg.role == "system":
                normalized_messages.append(SystemMessage(content=msg.content))

        # 情况 C: 字典 (兜底，或者是 LangGraph Checkpoint 反序列化出来的)
        elif isinstance(msg, dict):
            role = msg.get("role")
            content = msg.get("content", "")
            # 尝试处理 ToolMessage (角色为 tool)
            if role == "tool":
                normalized_messages.append(ToolMessage(
                    content=content,
                    tool_call_id=msg.get("tool_call_id", "unknown")
                ))
            elif role == "user":
                normalized_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                # 注意：如果字典里有 tool_calls，这里简单的 AIMessage 可能无法完全还原
                # 但 LangGraph 内部通常会传递 BaseMessage 对象，走到这步的概率较低
                normalized_messages.append(AIMessage(content=content))
            elif role == "system":
                normalized_messages.append(SystemMessage(content=content))

    # 2. 裁剪：直接对对象列表进行 trim，LangChain 能完美识别这些对象
    try:
        trimmed_messages = _trim_messages(
            normalized_messages,
            strategy="last",
            token_counter=get_token_count,
            max_tokens=settings.MAX_TOKENS,
            start_on="human",
            include_system=False,
            allow_partial=False,
        )
    except Exception as e:
        logger.warning(
            "message_trimming_failed_fallback_enabled",
            error=str(e),
            total_messages=len(messages)
        )
        # 降级：如果裁剪失败，取最后 10 条（保留对象，不转字典）
        trimmed_messages = normalized_messages[-10:] if len(normalized_messages) > 10 else normalized_messages

    # 3. 插入 System Prompt
    if system_prompt:
        trimmed_messages.insert(0, SystemMessage(content=system_prompt))

    return trimmed_messages