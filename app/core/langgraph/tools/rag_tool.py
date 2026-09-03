"""
知识库检索工具。

平台 Agent 通过工具调用按需检索知识库。检索范围（kbIds）、TopK、分数阈值
默认经 LangGraph 的 InjectedState 从图状态注入；`kb_id` 是 LLM 可选参数，
允许模型从「该 Agent 已绑定的知识库」中自选一个（工具描述会列出可用列表），
未填或越权时回退到绑定的完整 kbIds。检索本身调用主后端配置好的 knowledge-service 客户端。
"""

from typing import Annotated, List, Optional

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from app.core.logging import logger
from app.services.knowledge_client import knowledge_service_client


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
async def knowledge_base_search(
    query: str,
    kb_id: Optional[str] = None,
    kb_ids: Annotated[List[str], InjectedState("knowledge_kb_ids")] = [],
    top_k: Annotated[int, InjectedState("knowledge_top_k")] = 5,
    min_score: Annotated[float, InjectedState("knowledge_score_threshold")] = 0.0,
) -> str:
    """从平台知识库检索文档内容。

    当问题需要项目特定文档、业务流程或平台配置依据时优先调用此工具。
    query 参数请用简洁关键词（如「OPC企业 扶持政策」），不要用完整问句，检索效果更好。
    kb_id 可选：从「可用知识库」列表中选择一个精确的知识库；不填则检索全部已绑定知识库。
    """
    bound_ids = kb_ids or []
    if kb_id:
        normalized = str(kb_id).strip()
        if normalized in bound_ids:
            bound_ids = [normalized]
        else:
            logger.warning("knowledge_base_search_kb_not_bound", kb_id=normalized, bound_ids=bound_ids)
    return await _search(query, bound_ids, top_k, min_score)


knowledge_base_tool = knowledge_base_search
