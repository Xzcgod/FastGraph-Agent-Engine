"""
检索算法策略层。

把检索从 service.py 里抽成可插拔策略：`search()` 是薄分发器，根据请求里的
`strategy` 字段（缺省走配置的默认策略）查找并调用对应的 `SearchStrategy`。
新增算法只需实现 `SearchStrategy` 并 `register_strategy`，便于后续多种算法
A/B 评估（评估服务黑盒调 /search 时传不同 strategy 即可）。

当前内置 `VectorSearchStrategy`：HNSW 向量召回（oversample）+ metadata SQL 粗筛
+ Python 精筛 + rerank。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, TypedDict

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.knowledge_service.config import settings
from services.knowledge_service.models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from services.knowledge_service.service import (
    get_embedding,
    metadata_matches,
    problem,
    rerank_items,
)


class SearchHit(TypedDict, total=False):
    """单条检索命中项，字段与对外契约（camelCase）一致。"""

    kbId: str
    kbName: str
    namespace: str
    documentId: str
    chunkId: str
    title: str
    sourceType: str
    sourceRef: str | None
    score: float
    distance: float
    contentExcerpt: str
    rerankScore: float | None
    citation: Dict[str, Any]


@dataclass(slots=True)
class SearchContext:
    """一次检索请求的归一化上下文。"""

    query: str
    kb_ids: List[str]
    top_k: int
    min_score: float
    metadata_filter: Dict[str, Any]
    namespace: str | None
    strategy: str | None = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "SearchContext":
        query = str(payload.get("query") or "").strip()
        if not query:
            raise problem(status.HTTP_400_BAD_REQUEST, "INVALID_QUERY", "query is required")
        top_k = max(1, min(int(payload.get("topK") or payload.get("top_k") or 5), 20))
        min_score = float(payload.get("minScore") or payload.get("scoreThreshold") or 0)

        kb_ids = payload.get("kbIds") or payload.get("kb_ids") or []
        single_kb_id = payload.get("kbId") or payload.get("kb_id")
        if single_kb_id and not kb_ids:
            kb_ids = [single_kb_id]
        if kb_ids is None:
            kb_ids = []
        if not isinstance(kb_ids, list):
            raise problem(status.HTTP_400_BAD_REQUEST, "INVALID_KB_IDS", "kbIds must be an array")

        metadata_filter = payload.get("metadataFilter") or {}
        if not isinstance(metadata_filter, dict):
            raise problem(status.HTTP_400_BAD_REQUEST, "INVALID_METADATA_FILTER", "metadataFilter must be an object")

        namespace = payload.get("namespace")
        strategy = payload.get("strategy")
        return cls(
            query=query,
            kb_ids=[str(kb_id) for kb_id in kb_ids],
            top_k=top_k,
            min_score=min_score,
            metadata_filter=metadata_filter,
            namespace=str(namespace) if namespace else None,
            strategy=str(strategy).strip().lower() if strategy else None,
        )


class SearchStrategy(Protocol):
    """检索策略接口。"""

    name: str

    async def search(self, session: AsyncSession, ctx: SearchContext) -> List[SearchHit]: ...


STRATEGIES: Dict[str, SearchStrategy] = {}


def register_strategy(strategy: SearchStrategy) -> None:
    """注册检索策略（按 name 索引）。"""
    STRATEGIES[strategy.name] = strategy


def get_strategy(name: str) -> SearchStrategy | None:
    return STRATEGIES.get(name)


# 顶层嵌套元数据段：metadataFilter 里这三个键会被当作精确路径下钻，而非扁平别名。
_NESTED_SECTIONS = ("common", "domain", "_raw")


def _json_text_eq(path: List[str], value: Any) -> Any:
    """构造 JSONB 标量相等谓词：metadata_json -> p1 -> ... ->> pn == str(value)。"""
    expression = KnowledgeDocument.metadata_json
    for part in path[:-1]:
        expression = expression.op("->")(part)
    expression = expression.op("->>")(path[-1])
    return expression == str(value)


def _nested_scalars(value: Dict[str, Any], prefix: List[str]) -> List[tuple[List[str], Any]]:
    """递归收集嵌套段里可下推的标量叶子（str/int/float；list/bool 交给 Python 精筛）。"""
    leaves: List[tuple[List[str], Any]] = []
    for key, item in value.items():
        if isinstance(item, dict):
            leaves.extend(_nested_scalars(item, prefix + [str(key)]))
        elif isinstance(item, (str, int, float)) and not isinstance(item, bool):
            leaves.append((prefix + [str(key)], item))
    return leaves


def _metadata_sql_conditions(metadata_filter: Dict[str, Any]) -> List[Any]:
    """把 metadataFilter 里可下推的标量条件转成 SQL 谓词（AND 连接）。

    - 嵌套段（common/domain/_raw）下的标量：精确路径相等。
    - 扁平标量 key：OR 匹配 common/domain/_raw 三个路径（对应 metadata_matches 的 aliases 展开）。
    - list/bool 等复杂形态不下推，交由 Python 精筛兜底。
    """
    conditions: List[Any] = []
    for key, value in metadata_filter.items():
        if isinstance(value, dict) and key in _NESTED_SECTIONS:
            for path, scalar in _nested_scalars(value, [key]):
                conditions.append(_json_text_eq(path, scalar))
        elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
            alternatives = [_json_text_eq([section, key], value) for section in _NESTED_SECTIONS]
            conditions.append(or_(*alternatives))
    return conditions


class VectorSearchStrategy:
    """纯向量检索：HNSW 召回 + metadata 粗筛 + Python 精筛 + rerank。"""

    name = "vector"

    async def search(self, session: AsyncSession, ctx: SearchContext) -> List[SearchHit]:
        # 预检：无任何可检索分片时直接返回空，省一次 embedding 调用。
        searchable_statement = (
            select(KnowledgeChunk.id)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .join(KnowledgeBase, KnowledgeChunk.kb_id == KnowledgeBase.id)
            .where(
                KnowledgeBase.status == "active",
                KnowledgeDocument.ingest_status == "completed",
                KnowledgeChunk.status == "active",
            )
            .limit(1)
        )
        if ctx.kb_ids:
            searchable_statement = searchable_statement.where(KnowledgeBase.id.in_(ctx.kb_ids))
        if ctx.namespace:
            searchable_statement = searchable_statement.where(KnowledgeBase.namespace == ctx.namespace)
        searchable_chunk_id = await session.scalar(searchable_statement)
        if not searchable_chunk_id:
            return []
        await session.rollback()

        query_vector = await get_embedding(ctx.query)
        distance = KnowledgeChunk.embedding.cosine_distance(query_vector).label("distance")
        candidate_limit = ctx.top_k * settings.search_oversample_factor

        conditions = [
            KnowledgeBase.status == "active",
            KnowledgeDocument.ingest_status == "completed",
            KnowledgeChunk.status == "active",
        ]
        if ctx.kb_ids:
            conditions.append(KnowledgeBase.id.in_(ctx.kb_ids))
        if ctx.namespace:
            conditions.append(KnowledgeBase.namespace == ctx.namespace)
        conditions.extend(_metadata_sql_conditions(ctx.metadata_filter))

        statement = (
            select(KnowledgeChunk, KnowledgeDocument, KnowledgeBase, distance)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .join(KnowledgeBase, KnowledgeChunk.kb_id == KnowledgeBase.id)
            .where(*conditions)
            .order_by(distance)
            .limit(candidate_limit)
        )
        rows = (await session.execute(statement)).all()

        items: List[SearchHit] = []
        for chunk, document, kb, raw_distance in rows:
            # Python 精筛：复杂形态（list/bool/递归 dict/aliases）在这里兜底，保证语义不回归。
            if not metadata_matches(ctx.metadata_filter, document.metadata_json or {}, chunk.metadata_json or {}):
                continue
            score = max(0.0, 1.0 - float(raw_distance or 0.0))
            if score < ctx.min_score:
                continue
            items.append(
                {
                    "kbId": kb.id,
                    "kbName": kb.name,
                    "namespace": kb.namespace,
                    "documentId": document.id,
                    "chunkId": chunk.id,
                    "title": document.title,
                    "sourceType": document.source_type,
                    "sourceRef": document.source_ref,
                    "score": round(score, 6),
                    "distance": float(raw_distance or 0.0),
                    "contentExcerpt": chunk.content_text[:800],
                    "citation": {
                        "documentId": document.id,
                        "chunkId": chunk.id,
                        "title": document.title,
                        "sourceRef": document.source_ref,
                    },
                }
            )

        reranked = await rerank_items(ctx.query, items)
        return reranked[: ctx.top_k]


register_strategy(VectorSearchStrategy())


async def search(session: AsyncSession, payload: Dict[str, Any]) -> Dict[str, Any]:
    """检索分发器：解析请求 → 选策略 → 执行 → 返回 items。"""
    ctx = SearchContext.from_payload(payload)
    strategy_name = ctx.strategy or settings.default_search_strategy
    strategy = get_strategy(strategy_name)
    if strategy is None:
        raise problem(
            status.HTTP_400_BAD_REQUEST,
            "UNKNOWN_STRATEGY",
            f"unknown search strategy: {strategy_name}",
        )
    hits = await strategy.search(session, ctx)
    return {"items": hits, "total": len(hits)}
