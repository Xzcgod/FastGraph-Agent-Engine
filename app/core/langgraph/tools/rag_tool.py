"""
知识库检索工具。

平台 Agent 通过工具调用按需检索知识库。检索范围（kbIds）、TopK、分数阈值
通过 LangGraph 的 InjectedState 从图状态注入，对 LLM 不可见，避免 LLM 自行
决定检索范围；检索本身调用主后端配置好的 knowledge-service 客户端。
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, List

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from app.core.logging import logger
from app.services.knowledge_client import knowledge_service_client


_thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rag_tool")


def _run_async_safely(coro):
    """在独立线程的事件循环中执行异步协程（工具是同步函数）。"""

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    return _thread_pool.submit(run).result()


async def _search(query: str, kb_ids: List[str], top_k: int, min_score: float) -> str:
    try:
        payload = await knowledge_service_client.post_json(
            "/internal/v1/kb/search",
            {
                "query": query,
                "kbIds": kb_ids,
                "topK": top_k,
                "minScore": min_score,
            },
        )
        items = payload.get("items", []) if isinstance(payload, dict) else []
        if not items:
            return "未检索到匹配知识。请如实告知用户文档中没有包含此信息。"

        parts = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("documentId") or "Untitled"
            kb_name = item.get("kbName") or item.get("kbId") or "knowledge-base"
            excerpt = item.get("contentExcerpt") or ""
            parts.append(f"--- 片段 {index} | {kb_name} | {title} ---\n{excerpt}")
        return "检索到的相关文档内容：\n" + "\n\n".join(parts)
    except Exception as exc:
        logger.exception("knowledge_base_search_failed", error=str(exc))
        return "检索失败：knowledge-service 当前不可用或返回异常。"


@tool
def knowledge_base_search(
    query: str,
    kb_ids: Annotated[List[str], InjectedState("knowledge_kb_ids")],
    top_k: Annotated[int, InjectedState("knowledge_top_k")],
    min_score: Annotated[float, InjectedState("knowledge_score_threshold")],
) -> str:
    """从平台知识库检索文档内容。

    当问题需要项目特定文档、业务流程或平台配置依据时优先调用此工具。
    检索范围已由平台管理员绑定到当前 Agent，无需也无法自行指定知识库。
    """
    return _run_async_safely(_search(query, kb_ids, top_k, min_score))


knowledge_base_tool = knowledge_base_search
