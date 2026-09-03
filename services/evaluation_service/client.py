"""HTTP client for knowledge-service evaluation calls."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from services.evaluation_service.schemas import KnowledgeDocumentRecord, KnowledgeSearchItem
from services.evaluation_service.settings import RetrievalEvalConfig


class KnowledgeServiceError(RuntimeError):
    """Raised when knowledge-service returns an error."""

    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class KnowledgeServiceClient:
    """Thin async client for the retrieval endpoints."""

    def __init__(self, config: RetrievalEvalConfig) -> None:
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=config.knowledge_service_base_url.rstrip("/"),
            timeout=httpx.Timeout(config.timeout_seconds),
        )

    async def aclose(self) -> None:
        if not self._client.is_closed:
            await self._client.aclose()

    def _headers(self, trace_id: str | None = None) -> Dict[str, str]:
        """组装服务间认证头：X-KB-Service-Token 校验 + 可选 X-Trace-Id 透传追踪。"""
        headers = {
            "X-KB-Service-Token": self.config.knowledge_service_token,
        }
        if trace_id:
            headers["X-Trace-Id"] = trace_id
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        trace_id: str | None = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
    ) -> Any:
        """底层请求：拼认证头、过滤空参数、解析 JSON，≥400 统一抛 KnowledgeServiceError。"""
        try:
            response = await self._client.request(
                method,
                path,
                headers=self._headers(trace_id=trace_id),
                params={key: value for key, value in (params or {}).items() if value not in (None, "")},
                json=json_body,
            )
        except httpx.HTTPError as exc:
            raise KnowledgeServiceError(f"request failed for {path}") from exc

        content_type = response.headers.get("content-type", "")
        payload: Any
        if "application/json" in content_type:
            try:
                payload = response.json()
            except ValueError as exc:
                raise KnowledgeServiceError(f"invalid json response from {path}") from exc
        else:
            payload = response.text

        if response.status_code >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else payload
            if isinstance(detail, dict):
                detail_message = detail.get("message") or detail.get("code") or detail
            else:
                detail_message = detail
            raise KnowledgeServiceError(
                f"{method} {path} -> {response.status_code}: {detail_message}",
                status_code=response.status_code,
                payload=payload,
            )
        return payload

    async def list_documents(self, kb_id: str, *, page: int, page_size: int) -> Dict[str, Any]:
        """分页拉取知识库文档目录，供评测建全量索引。"""
        path = self.config.documents_path_template.format(kb_id=kb_id)
        payload = await self.request(
            "GET",
            path,
            trace_id=f"eval-catalog-{kb_id}-{page}",
            params={
                "page": page,
                "pageSize": page_size,
                "includeArchived": False,
            },
        )
        if not isinstance(payload, dict):
            raise KnowledgeServiceError(f"unexpected document payload for {kb_id}")
        return payload

    async def search(
        self,
        *,
        query: str,
        kb_ids: List[str],
        top_k: int,
        score_threshold: float,
        trace_id: str,
        metadata_filter: Dict[str, Any] | None = None,
        namespace: str | None = None,
        strategy: str | None = None,
    ) -> List[KnowledgeSearchItem]:
        """调用检索接口并把结果归一为 KnowledgeSearchItem 列表。strategy 可选，透传给 knowledge-service 切换检索算法。"""
        body: Dict[str, Any] = {
            "query": query,
            "kbIds": kb_ids,
            "topK": top_k,
            "minScore": score_threshold,
            "metadataFilter": metadata_filter or {},
            "namespace": namespace,
        }
        if strategy:
            body["strategy"] = strategy
        payload = await self.request(
            "POST",
            self.config.search_path,
            trace_id=trace_id,
            json_body=body,
        )
        if not isinstance(payload, dict):
            raise KnowledgeServiceError("unexpected search payload")
        items = payload.get("items") or []
        if not isinstance(items, list):
            raise KnowledgeServiceError("search payload items must be a list")
        return [KnowledgeSearchItem.model_validate(item) for item in items if isinstance(item, dict)]

    @staticmethod
    def parse_documents(payload: Dict[str, Any]) -> list[KnowledgeDocumentRecord]:
        """把文档目录接口返回体解析为 KnowledgeDocumentRecord 列表。"""
        items = payload.get("items") or []
        if not isinstance(items, list):
            raise KnowledgeServiceError("document payload items must be a list")
        return [KnowledgeDocumentRecord.model_validate(item) for item in items if isinstance(item, dict)]
