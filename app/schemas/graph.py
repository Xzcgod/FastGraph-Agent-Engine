"""LangGraph 状态图 Schema 定义。

升级内容：
- 新增 summary 字段：存储滚动摘要（短期记忆压缩）
- 新增 active_features 字段：传递当前激活的功能开关
- 移除 long_term_memory 字段：记忆改为工具化，不再注入 Prompt

⚠️ 重要：修改此文件后必须执行 `docker-compose down -v` 清空旧 Checkpoint 数据
"""

from typing import Annotated, Dict, Optional

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class GraphState(BaseModel):
    """LangGraph Agent 的状态定义。"""

    # 消息列表（使用 add_messages 支持增量更新）
    messages: Annotated[list, add_messages] = Field(
        default_factory=list,
        description="当前对话消息列表",
    )

    # ✅ 新增：短期记忆滚动摘要
    # 当消息超过 SUMMARY_THRESHOLD 时，旧消息被压缩为此文本
    summary: str = Field(
        default="",
        description="历史对话的滚动摘要，用于压缩旧消息减少 Token 消耗",
    )

    # ✅ 新增：当前激活的功能开关
    # 从 ChatRequest.features 传入，决定 call_model 时绑定哪些工具
    active_features: Optional[Dict[str, bool]] = Field(
        default=None,
        description="当前激活的功能特性开关，由前端请求传入",
    )