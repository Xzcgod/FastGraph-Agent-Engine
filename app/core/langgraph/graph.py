"""LangGraph Agent 核心工作流。

包含：状态定义 (GraphState) 和 核心逻辑类 (Chatbot)。

修复记录：
- [Fix-Auth-Fatal] 修复数据库认证错误。
- [Fix-Pool-Lifecycle] 修复连接池生命周期问题。
- [Feature-Approval] ✅ 新增：在 astream_response 结束前检查中断状态。
  如果发现 graph 处于暂停状态（snapshot.next），强制发送审批提示，唤醒前端 UI。
"""

import asyncio
from typing import Annotated, Dict, List, Optional, Any, AsyncGenerator, Union

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    BaseMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import logger
from app.core.prompts import load_system_prompt
from app.models.session import Session
from app.schemas.chat import Message as ApiMessage
from app.schemas.graph import GraphState
from app.services.llm import llm_service
from app.utils.graph import prepare_messages


class Chatbot:
    def __init__(self):
        self._graph = None
        self._pool: Optional[AsyncConnectionPool] = None
        self._initialized = False

    async def _get_connection_pool(self) -> AsyncConnectionPool:
        """获取或创建异步数据库连接池（单例模式）"""
        if self._pool is None:
            connection_kwargs = {
                "autocommit": True,
                "prepare_threshold": 0,
            }
            # 格式化连接字符串
            db_url = (
                f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
                f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
            )

            self._pool = AsyncConnectionPool(
                conninfo=db_url,
                max_size=20,
                kwargs=connection_kwargs,
                open=False
            )
            logger.info("langgraph_async_db_pool_created")
        return self._pool

    async def initialize(self):
        """初始化 Graph 和 Checkpointer"""
        if self._initialized:
            return

        pool = await self._get_connection_pool()
        await pool.open()
        await pool.wait()

        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        logger.info("langgraph_checkpointer_setup_success")

        self._graph = self.create_graph(checkpointer)
        self._initialized = True

    def _call_model(self, state: GraphState, config: RunnableConfig):
        """核心节点：调用 LLM"""
        features = state.active_features or {}

        tools = []
        from app.core.langgraph.tools import all_tools_map, base_tools
        tools.extend(base_tools)
        for feature_key, tool_list in all_tools_map.items():
            if features.get(feature_key, False):
                tools.extend(tool_list)

        model = llm_service.get_llm()
        if tools:
            model = model.bind_tools(tools)

        instructions = []
        if features.get("knowledge_base"):
            rag_instruction = (
                "\n\n### 🚨 CRITICAL RULE: KNOWLEDGE BASE MODE ACTIVE\n"
                "用户已开启【强制知识库检索模式】。你必须遵守以下 **最高优先级** 协议：\n\n"
                "1. **禁止直接回答**：对于用户的任何问题，**绝对禁止**直接使用你的预训练知识回答。\n"
                "2. **必须检索**：你必须 **FIRST AND FOREMOST** 调用 `knowledge_base_search` 工具进行检索。\n"
                "3. **无结果才降级**：只有当 `knowledge_base_search` 返回 '未找到相关文档' 后，你才被允许使用通用知识回答。"
            )
            instructions.append(rag_instruction)

        if features.get("code_interpreter"):
            instructions.append("\n- 用户已授权代码执行。遇到计算问题，优先使用 python_repl。")

        system_prompt = load_system_prompt(
            user_id=config.get("configurable", {}).get("user_id", "unknown"),
            summary=state.summary,
            custom_instructions="\n".join(instructions)
        )

        messages = prepare_messages(state.messages, llm=model, system_prompt=system_prompt)
        response = model.invoke(messages, config)
        return {"messages": [response]}

    def create_graph(self, checkpointer):
        """构建 LangGraph 状态机"""
        workflow = StateGraph(GraphState)
        workflow.add_node("agent", self._call_model)

        from app.core.langgraph.tools import all_tools_map, base_tools
        all_tools = list(base_tools)
        for tools in all_tools_map.values():
            all_tools.extend(tools)

        tool_node = ToolNode(all_tools)
        workflow.add_node("tools", tool_node)

        workflow.add_edge(START, "agent")

        def should_continue(state: GraphState):
            messages = state.messages
            last_message = messages[-1]
            if last_message.tool_calls:
                return "tools"
            return END

        workflow.add_conditional_edges("agent", should_continue, ["tools", END])
        workflow.add_edge("tools", "agent")

        return workflow.compile(checkpointer=checkpointer)

    async def get_response(self, session_id: str, messages: List[ApiMessage], features: Dict[str, bool], user_id: str) -> List[ApiMessage]:
        """普通请求入口"""
        await self.initialize()
        config = {"configurable": {"thread_id": session_id, "user_id": user_id}}
        input_messages = [{"role": m.role, "content": m.content} for m in messages]
        input_state = {"messages": input_messages, "active_features": features}

        final_state = await self._graph.ainvoke(input_state, config)
        all_messages = final_state["messages"]
        last_message = all_messages[-1]
        return [ApiMessage(role="assistant", content=last_message.content)]

    async def astream_response(
        self,
        session_id: str,
        messages: List[ApiMessage],
        features: Dict[str, bool],
        user_id: str
    ) -> AsyncGenerator[str, None]:
        """流式生成回复"""
        await self.initialize()

        config = {
            "configurable": {
                "thread_id": session_id,
                "user_id": user_id
            }
        }

        input_messages = [{"role": m.role, "content": m.content} for m in messages]
        input_state = {"messages": input_messages, "active_features": features}

        # 1. 正常的流式输出
        async for event in self._graph.astream(input_state, config, stream_mode="messages"):
            chunk, metadata = event

            # 处理 AI 回复
            if isinstance(chunk, AIMessage) and metadata.get("langgraph_node") == "agent":
                content = chunk.content
                if content:
                    yield content

                # ✅ [Feature] 可视化思维链：如果有工具调用，输出提示
                if chunk.tool_calls:
                    tool_names = ", ".join([t['name'] for t in chunk.tool_calls])
                    # 使用特殊的引用格式，前端可以解析并显示为“正在思考”
                    yield f"\n\n> ⚙️ **正在调用工具**: `{tool_names}`... \n\n"

        # 2. ✅ [Critical Fix] 检查是否被中断 (Interrupt)
        # 这一步至关重要：如果图停下来了，说明需要人工介入。我们必须告诉前端。
        snapshot = await self._graph.aget_state(config)
        if snapshot.next:
            # 发送特定的标记，前端检测到这个标记就会弹出审批卡片
            yield "\n\n⚠️ **安全拦截**: 系统已生成敏感操作请求（如发送邮件）。\n程序已暂停，请在上方出现的**审批卡片**中点击 [批准] 或 [拒绝] 以继续。"

    async def resume_graph(self, session_id: str, approved: bool) -> str:
        """恢复暂停的图"""
        await self.initialize()
        config = {"configurable": {"thread_id": session_id}}

        snapshot = await self._graph.aget_state(config)
        if not snapshot.next:
            return "当前会话没有待处理的暂停任务。"

        resume_val = "approved" if approved else "rejected"
        await self._graph.ainvoke(Command(resume=resume_val), config=config)
        return "✅ 操作已确认，任务继续执行。" if approved else "🚫 操作已驳回。"

    async def get_chat_history(self, session_id: str) -> List[ApiMessage]:
        await self.initialize()
        state = await self._graph.aget_state({"configurable": {"thread_id": session_id}})
        if not state.values:
            return []
        return self._convert_state_to_api(state.values.get("messages", []))

    async def clear_chat_history(self, session_id: str):
        pool = await self._get_connection_pool()
        async with pool.connection() as conn:
             async with conn.transaction():
                 await conn.execute("DELETE FROM checkpoints WHERE thread_id = %s", [session_id])
                 await conn.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", [session_id])
                 await conn.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", [session_id])
        logger.info("chat_history_cleared", session_id=session_id)

    def _convert_state_to_api(self, messages: List[BaseMessage]) -> List[ApiMessage]:
        api_messages = []
        for msg in messages:
            role = "user"
            if isinstance(msg, AIMessage):
                role = "assistant"
            elif isinstance(msg, SystemMessage):
                role = "system"
            elif isinstance(msg, ToolMessage):
                continue
            api_messages.append(ApiMessage(role=role, content=str(msg.content)))
        return api_messages

from app.services.database import database_service
chatbot = Chatbot()