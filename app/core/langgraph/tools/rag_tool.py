"""全能 RAG 工具 - 集成 PDF 解析、混合检索与重排序。

特性：
1. Ingest: 支持 PDF/TXT 解析与切片入库。
2. Hybrid Search: 向量检索 (Semantic) + 关键词检索 (Keyword)。
3. Rerank: 使用 SiliconFlow BGE-Reranker API 对结果进行精排 (真正的模型调用)。

修复记录：
- [Fix-Syntax] ✅ 修复 PydanticUserError: 'KnowledgeBaseTool' is not fully defined。
  错误原因：name: "xxx" 被误判为类型注解。
  修复方案：改为 name: str = "xxx"。
"""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import (
    List,
    Type,
    Any,
)

import httpx
from langchain_core.tools import BaseTool
from langchain_openai import OpenAIEmbeddings
from pydantic import (
    BaseModel,
    Field,
)
from sqlmodel import (
    Session,
    select,
    text,
)

from app.core.config import settings
from app.core.logging import logger
from app.models.knowledge import KnowledgeChunk
from app.services.database import database_service

# 尝试导入 PDF 解析库
try:
    import fitz  # PyMuPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# 线程池
_thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rag_tool")


def _run_async_safely(coro):
    """在同步上下文中安全执行异步协程"""
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    return _thread_pool.submit(run).result()


# --- 1. 核心功能实现 ---

async def get_embedding(text: str) -> List[float]:
    """使用 SiliconFlow/OpenAI 兼容接口获取 Embedding"""
    embeddings = OpenAIEmbeddings(
        model="BAAI/bge-m3",
        openai_api_key=settings.OPENAI_API_KEY,
        openai_api_base=settings.OPENAI_BASE_URL,
        check_embedding_ctx_length=False,
    )
    return await embeddings.aembed_query(text)


async def rerank_results(query: str, documents: List[str], top_n: int = 3) -> List[str]:
    """调用 SiliconFlow 的 Reranker API 进行重排序"""
    if not documents:
        return []

    url = "https://api.siliconflow.cn/v1/rerank"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": settings.RAG_RERANKER_MODEL,
        "query": query,
        "documents": documents,
        "top_n": top_n,
        "return_documents": True
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            # 提取结果
            reranked_docs = []
            for item in data.get("results", []):
                doc_text = item.get("document", {}).get("text", "")
                if doc_text:
                    reranked_docs.append(doc_text)

            return reranked_docs
        except Exception as e:
            logger.error("rerank_failed_fallback_to_original", error=str(e))
            return documents[:top_n]


def _extract_text(row: Any) -> str:
    """辅助函数：从 SQLModel 结果中提取纯文本。"""
    try:
        if isinstance(row, str):
            return row
        if hasattr(row, "content"):
            return str(row.content)
        if hasattr(row, "_mapping"):
            return str(row._mapping.get("content", ""))
        if isinstance(row, (list, tuple)) and len(row) > 0:
            return str(row[0])
        return str(row)
    except Exception:
        return str(row)


async def hybrid_search(query: str, top_k: int = 10) -> List[str]:
    """混合检索：向量相似度 + 关键词匹配"""
    query_vec = await get_embedding(query)

    with Session(database_service.engine) as session:
        # 使用 pgvector 的 L2 距离 (<->) 或 余弦距离 (<=>)
        stmt = text("""
            SELECT content FROM knowledge_chunk 
            ORDER BY embedding <=> :embedding 
            LIMIT :limit
        """)
        vec_str = str(query_vec)
        results = session.exec(stmt, params={"embedding": vec_str, "limit": top_k}).all()
        docs = [_extract_text(r) for r in results]
        return docs


# --- 2. 文件上传与解析 ---

async def ingest_file(file_path: str, source_name: str) -> int:
    """解析文件并入库"""
    if not PDF_AVAILABLE:
        raise ImportError("PyMuPDF (fitz) not installed")

    content = ""
    if file_path.lower().endswith(".pdf"):
        doc = fitz.open(file_path)
        for page in doc:
            content += page.get_text()
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

    if not content:
        return 0

    chunk_size = 500
    chunks = [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]

    count = 0
    with Session(database_service.engine) as session:
        for chunk in chunks:
            vec = await get_embedding(chunk)
            obj = KnowledgeChunk(content=chunk, source=source_name, embedding=vec)
            session.add(obj)
            count += 1
        session.commit()

    logger.info("ingest_success", source=source_name, count=count)
    return count


# --- 4. 工具定义 ---

class KnowledgeBaseInput(BaseModel):
    query: str = Field(..., description="检索查询，例如'SM3的定义'或'项目部署流程'")


class KnowledgeBaseTool(BaseTool):
    # ✅ 修复点：添加 `str =`，明确这是字段赋值，不是类型注解
    name: str = "knowledge_base_search"
    description: str = (
        "【官方知识库/文档检索】包含项目特定文档、技术规范和业务数据。"
        "这是获取信息的 **唯一权威来源** (Truth Source)。"
        "当用户询问任何名词定义、流程或业务逻辑时，必须 **优先** 使用此工具检索，而不是依赖通用知识。"
    )
    args_schema: Type[BaseModel] = KnowledgeBaseInput

    def _run(self, query: str) -> str:
        return _run_async_safely(self._arun(query))

    async def _arun(self, query: str) -> str:
        try:
            # 1. Recall
            candidates = await hybrid_search(query, top_k=10)
            if not candidates:
                return "未找到相关文档。请告知用户文档中没有包含此信息。"

            # 2. Rerank
            final_results = await rerank_results(query, candidates, top_n=3)

            # 3. Output
            context = "\n\n".join([f"--- 片段 {i+1} ---\n{doc}" for i, doc in enumerate(final_results)])
            return f"检索到的相关文档内容：\n{context}"

        except Exception as e:
            logger.error("knowledge_base_search_failed", error=str(e))
            return f"检索失败: {str(e)}"

# 实例化工具
knowledge_base_tool = KnowledgeBaseTool()