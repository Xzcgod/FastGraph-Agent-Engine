"""
检索算法策略层。

把检索从 service.py 里抽成可插拔策略：`search()` 是薄分发器，根据请求里的
`strategy` 字段（缺省走配置的默认策略）查找并调用对应的 `SearchStrategy`。
新增算法只需实现 `SearchStrategy` 并 `register_strategy`，便于后续多种算法
A/B 评估（评估服务黑盒调 /search 时传不同 strategy 即可）。

内置三个策略：
- `vector`：纯向量检索（HNSW 召回 + metadata SQL 粗筛 + Python 精筛 + rerank）。
- `weighted`：在向量分之上融合区域/时效/产业的业务软偏好（固定规则 + metadataFilter）。
- `hybrid`：pg_trgm 关键词通道 + pgvector 向量通道，RRF 融合。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, Set, Tuple, TypedDict

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
    weightedScore: float | None
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
    rerank: bool = True

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
        rerank = bool(payload.get("rerank", True))
        return cls(
            query=query,
            kb_ids=[str(kb_id) for kb_id in kb_ids],
            top_k=top_k,
            min_score=min_score,
            metadata_filter=metadata_filter,
            namespace=str(namespace) if namespace else None,
            strategy=str(strategy).strip().lower() if strategy else None,
            rerank=rerank,
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
# 区域优先级权重（对齐评估服务 runner 的 _region_rank）。
_REGION_RANK = {"武汉": 3, "湖北": 2, "国家": 1}

# 召回条目：(chunk, document, kb, distance, score)。distance 对关键词通道为 None。
RecallEntry = Tuple[KnowledgeChunk, KnowledgeDocument, KnowledgeBase, float | None, float]


def _json_text_eq(path: List[str], value: Any) -> Any:
    """构造 JSONB 标量相等谓词：metadata_json -> p1 -> ... ->> pn == str(value)。"""
    expression = KnowledgeDocument.metadata_json
    for part in path[:-1]:
        expression = expression.op("->")(part)
    expression = expression.op("->>")(path[-1])
    return expression == str(value)


def _nested_scalars(value: Dict[str, Any], prefix: List[str]) -> List[Tuple[List[str], Any]]:
    """递归收集嵌套段里可下推的标量叶子（str/int/float；list/bool 交给 Python 精筛）。"""
    leaves: List[Tuple[List[str], Any]] = []
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


def _base_conditions(ctx: SearchContext) -> List[Any]:
    """检索通道共用的基础过滤条件（kb 范围 / namespace / 状态）。"""
    conditions: List[Any] = [
        KnowledgeBase.status == "active",
        KnowledgeDocument.ingest_status == "completed",
        KnowledgeChunk.status == "active",
    ]
    if ctx.kb_ids:
        conditions.append(KnowledgeBase.id.in_(ctx.kb_ids))
    if ctx.namespace:
        conditions.append(KnowledgeBase.namespace == ctx.namespace)
    return conditions


async def _has_searchable_chunk(session: AsyncSession, ctx: SearchContext) -> bool:
    """预检：无任何可检索分片时返回 False，省一次 embedding 调用。"""
    statement = (
        select(KnowledgeChunk.id)
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .join(KnowledgeBase, KnowledgeChunk.kb_id == KnowledgeBase.id)
        .where(*_base_conditions(ctx))
        .limit(1)
    )
    searchable_chunk_id = await session.scalar(statement)
    if not searchable_chunk_id:
        return False
    await session.rollback()
    return True


async def _vector_recall(session: AsyncSession, ctx: SearchContext, limit: int) -> List[RecallEntry]:
    """向量召回：HNSW cosine_distance 排序，metadata SQL 粗筛 + Python 精筛 + min_score。"""
    query_vector = await get_embedding(ctx.query)
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector).label("distance")
    conditions = _base_conditions(ctx) + _metadata_sql_conditions(ctx.metadata_filter)
    statement = (
        select(KnowledgeChunk, KnowledgeDocument, KnowledgeBase, distance)
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .join(KnowledgeBase, KnowledgeChunk.kb_id == KnowledgeBase.id)
        .where(*conditions)
        .order_by(distance)
        .limit(limit)
    )
    rows = (await session.execute(statement)).all()

    entries: List[RecallEntry] = []
    for chunk, document, kb, raw_distance in rows:
        if not metadata_matches(ctx.metadata_filter, document.metadata_json or {}, chunk.metadata_json or {}):
            continue
        score = max(0.0, 1.0 - float(raw_distance or 0.0))
        if score < ctx.min_score:
            continue
        entries.append((chunk, document, kb, float(raw_distance or 0.0), score))
    return entries


def _keyword_bonus(query: str, chunk_text: str) -> float:
    """query 与 chunk 正文的字符 bigram 重叠率（0~1），衡量关键词命中程度。

    轻量替代 pg_trgm 全表扫描：只对已召回的候选在 Python 侧算，避免 GIN 索引
    全扫带来的高延迟；专有名词/政策名等「向量语义易漂移、字符强匹配」的 query
    能靠它得到加分。
    """
    q = _normalize_text(query)
    text = _normalize_text(chunk_text)
    if not q or len(q) < 2:
        return 0.0
    q_grams = {q[i : i + 2] for i in range(len(q) - 1)}
    if not q_grams:
        return 0.0
    text_grams = {text[i : i + 2] for i in range(len(text) - 1)}
    return len(q_grams & text_grams) / len(q_grams)


def _hit_to_dict(entry: RecallEntry, *, weighted_score: float | None = None) -> SearchHit:
    chunk, document, kb, raw_distance, score = entry
    hit: SearchHit = {
        "kbId": kb.id,
        "kbName": kb.name,
        "namespace": kb.namespace,
        "documentId": document.id,
        "chunkId": chunk.id,
        "title": document.title,
        "sourceType": document.source_type,
        "sourceRef": document.source_ref,
        "score": round(score, 6),
        "distance": round(raw_distance, 6) if raw_distance is not None else 0.0,
        "contentExcerpt": chunk.content_text[:800],
        "citation": {
            "documentId": document.id,
            "chunkId": chunk.id,
            "title": document.title,
            "sourceRef": document.source_ref,
        },
    }
    if weighted_score is not None:
        hit["weightedScore"] = round(weighted_score, 6)
    return hit


# --- 业务信号提取（对齐评估服务 runner 的口径，但独立实现避免跨服务耦合） ---

def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    normalized: List[str] = []
    seen: Set[str] = set()
    for item in items:
        text = _normalize_text(item)
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


def _metadata_flat(document_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """展平 document.metadata_json 的 _raw/common/domain 为扁平视图（对齐 runner _metadata_view）。"""
    view: Dict[str, Any] = {}
    for key in ("_raw", "common", "domain"):
        value = document_metadata.get(key)
        if isinstance(value, dict):
            view.update(value)
    view.update({key: value for key, value in document_metadata.items() if not str(key).startswith("_")})
    return view


def _normalize_region_label(value: Any) -> str:
    text = _normalize_text(value)
    if "武汉" in text:
        return "武汉"
    if "湖北" in text:
        return "湖北"
    if text in {"国家", "全国", "中央", "国家级"} or "国务院" in text or "中央" in text:
        return "国家"
    return text or "其他"


def _resolve_region(document_metadata: Dict[str, Any]) -> str:
    view = _metadata_flat(document_metadata)
    region = _normalize_text(view.get("region") or view.get("区域"))
    if region:
        return _normalize_region_label(region)
    city = _normalize_text(view.get("city") or view.get("城市"))
    province = _normalize_text(view.get("province") or view.get("省份"))
    if city:
        return "武汉"
    if province:
        return "湖北"
    return "国家"


def _document_year(document_metadata: Dict[str, Any]) -> int | None:
    view = _metadata_flat(document_metadata)
    value = view.get("publishedAt") or view.get("publishTime") or view.get("发布时间")
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _document_industry(document_metadata: Dict[str, Any]) -> List[str]:
    view = _metadata_flat(document_metadata)
    value = view.get("industry") or view.get("chain") or view.get("产业分类")
    return _normalize_list(value)


def _filter_value(metadata_filter: Dict[str, Any], *keys: str) -> Any:
    """从 metadataFilter 取偏好值：先查嵌套段（common/domain/_raw），再查扁平 key。"""
    for section in _NESTED_SECTIONS:
        nested = metadata_filter.get(section)
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if value not in (None, "", [], {}):
                    return value
    for key in keys:
        value = metadata_filter.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _preference_from_filter(metadata_filter: Dict[str, Any]) -> Tuple[str, int | None, Set[str]]:
    """解析加权偏好：region 默认「武汉」，year 默认 None（=最新），industry 默认空集。"""
    region_value = _filter_value(metadata_filter, "region", "区域")
    region = _normalize_region_label(region_value) if region_value else "武汉"

    year_value = _filter_value(metadata_filter, "year", "publishedAt", "publishTime", "发布时间", "年份")
    year: int | None = None
    if year_value is not None:
        match = re.search(r"(19|20)\d{2}", str(year_value))
        if match:
            year = int(match.group(0))

    industry = set(_normalize_list(_filter_value(metadata_filter, "industry", "chain", "产业分类")))
    return region, year, industry


def _weighted_bonus(
    document_metadata: Dict[str, Any],
    region_pref: str,
    reference_year: int | None,
    industry_pref: Set[str],
) -> float:
    """计算文档的业务加权加分（区域 + 时效 + 产业）。"""
    bonus = 0.0
    region = _resolve_region(document_metadata)
    bonus += (_REGION_RANK.get(region, 0) / 3.0) * settings.search_region_weight

    if reference_year is not None:
        doc_year = _document_year(document_metadata)
        if doc_year is not None:
            bonus += max(0.0, 1.0 - abs(reference_year - doc_year) / 5.0) * settings.search_freshness_weight

    if industry_pref:
        doc_industry = set(_document_industry(document_metadata))
        if doc_industry & industry_pref:
            bonus += settings.search_industry_weight
    return bonus


async def _maybe_rerank(ctx: SearchContext, items: List[SearchHit]) -> List[SearchHit]:
    """按 ctx.rerank 决定是否精排：关闭时直接返回，用于延迟敏感场景或评估 rerank 开关影响。"""
    if not ctx.rerank:
        return items
    return await rerank_items(ctx.query, items)


def _fuse_rerank(items: List[SearchHit]) -> List[SearchHit]:
    """把业务加权分（weightedScore 存纯 bonus）融合进精排结果：base + bonus 重排。

    rerank 开启时 base 取 rerankScore（否则取向量 score），再加上业务 bonus。
    这样业务加权不会在 rerank 之后被覆盖——加权是在精排结果上做软偏好微调。
    """
    def fused_score(item: SearchHit) -> float:
        base = item.get("rerankScore") if item.get("rerankScore") is not None else item.get("score", 0.0)
        return float(base) + float(item.get("weightedScore") or 0.0)

    return sorted(items, key=fused_score, reverse=True)


# --- 检索策略 ---

class VectorSearchStrategy:
    """纯向量检索：HNSW 召回 + metadata 粗筛 + Python 精筛 + rerank。"""

    name = "vector"

    async def search(self, session: AsyncSession, ctx: SearchContext) -> List[SearchHit]:
        if not await _has_searchable_chunk(session, ctx):
            return []
        entries = await _vector_recall(session, ctx, ctx.top_k * settings.search_oversample_factor)
        items = [_hit_to_dict(entry) for entry in entries]
        reranked = await _maybe_rerank(ctx, items)
        return reranked[: ctx.top_k]


class WeightedVectorSearchStrategy:
    """元数据加权排序：向量召回后按业务软偏好（区域/时效/产业）加分，rerank 后融合重排。"""

    name = "weighted"

    async def search(self, session: AsyncSession, ctx: SearchContext) -> List[SearchHit]:
        if not await _has_searchable_chunk(session, ctx):
            return []
        entries = await _vector_recall(session, ctx, ctx.top_k * settings.search_oversample_factor)
        if not entries:
            return []

        region_pref, year_pref, industry_pref = _preference_from_filter(ctx.metadata_filter)
        years = [year for entry in entries if (year := _document_year(entry[1].metadata_json or {})) is not None]
        reference_year = year_pref or (max(years) if years else None)

        # weightedScore 存纯业务 bonus，供 _fuse_rerank 在 rerank 后融合。
        items: List[SearchHit] = []
        for entry in entries:
            bonus = _weighted_bonus(entry[1].metadata_json or {}, region_pref, reference_year, industry_pref)
            items.append(_hit_to_dict(entry, weighted_score=bonus))

        reranked = await _maybe_rerank(ctx, items)
        fused = _fuse_rerank(reranked)
        return fused[: ctx.top_k]


class HybridSearchStrategy:
    """混合检索（轻量）：向量召回 + 关键词加分 + rerank 融合。

    不做 pg_trgm 全表关键词召回（成本高、收益低），改为对向量召回的候选在
    Python 侧算字符 bigram 重叠率加分，专有名词/政策名等 query 受益。
    """

    name = "hybrid"

    async def search(self, session: AsyncSession, ctx: SearchContext) -> List[SearchHit]:
        if not await _has_searchable_chunk(session, ctx):
            return []
        entries = await _vector_recall(session, ctx, ctx.top_k * settings.search_oversample_factor)
        if not entries:
            return []

        items: List[SearchHit] = []
        for entry in entries:
            chunk = entry[0]
            overlap = _keyword_bonus(ctx.query, chunk.content_text)
            bonus = overlap * settings.search_keyword_weight
            items.append(_hit_to_dict(entry, weighted_score=bonus))

        reranked = await _maybe_rerank(ctx, items)
        fused = _fuse_rerank(reranked)
        return fused[: ctx.top_k]


register_strategy(VectorSearchStrategy())
register_strategy(WeightedVectorSearchStrategy())
register_strategy(HybridSearchStrategy())


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
