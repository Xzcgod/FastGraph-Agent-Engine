# services/knowledge_service/ — 独立知识库微服务

本目录是独立的**知识库微服务**，负责知识库、文档、分片、入库任务和向量检索。主后端（`app/`）只做权限校验和代理，不直接访问这里的数据库，也不管理知识正文。

## 目录结构

```
knowledge_service/
├── __init__.py    # 包标记
├── config.py      # 配置：KNOWLEDGE_* 环境变量
├── db.py          # 数据库连接：async engine + init_database
├── extractors.py  # 文档文本抽取（PDF / 文本）
├── main.py        # FastAPI 入口 + /internal/v1/kb/* 路由 + 预热 embedding
├── models.py      # 数据模型（5 张表）
├── security.py    # 服务间认证（X-KB-Service-Token）
└── service.py     # 业务逻辑（切分/embedding/rerank/检索/入库任务）
```

## 各文件职责

| 文件 | 作用 |
|---|---|
| `config.py` | `Settings` 单例，读取 `KNOWLEDGE_*` 环境变量（embedding、rerank、chunk 切分、数据库连接、限流） |
| `db.py` | async engine + `AsyncSessionLocal` + `init_database`（建表 + pgvector 扩展）+ `session_dependency` |
| `extractors.py` | `extract_text_from_bytes`：从字节流抽取文本（PDF 用 PyMuPDF，文本文件多编码解码） |
| `main.py` | FastAPI 应用，`/internal/v1/kb/*` 路由，启动时预热 embedding 模型 |
| `models.py` | 5 张表：`te_knowledge_base`、`te_knowledge_document`、`td_knowledge_chunk`、`tl_knowledge_ingest_job`、`tl_knowledge_ingest_step` |
| `security.py` | `require_service_token`（校验 X-KB-Service-Token）+ `actor_from_headers`（透传操作人） |
| `service.py` | 业务核心：文本切分、embedding、rerank、向量检索、入库任务状态机 |

## 数据模型（5 张表）

| 表 | 类 | 作用 |
|---|---|---|
| `te_knowledge_base` | `KnowledgeBase` | 知识库（namespace/name/status/search_policy） |
| `te_knowledge_document` | `KnowledgeDocument` | 文档（title/source_ref/content_text/source_hash/ingest_status） |
| `td_knowledge_chunk` | `KnowledgeChunk` | 分片（content_text/embedding `Vector(1024)`/status） |
| `tl_knowledge_ingest_job` | `KnowledgeIngestJob` | 入库任务（status/source_hash/result） |
| `tl_knowledge_ingest_step` | `KnowledgeIngestStep` | 入库步骤（validate/parse/split/embed/save） |

## 阅读理解路线

1. **`main.py`** — 先看入口：路由挂载在 `/internal/v1/kb/*`，理解「只暴露内部 API + 启动时预热 embedding」。
2. **`models.py`** — 看数据模型：5 张表，理解「知识库 → 文档 → 分片」和「入库任务 → 步骤」的层级关系。
3. **`config.py`** — 看配置：`KNOWLEDGE_*` 环境变量，embedding 默认指向本地 Ollama 的 `bge-m3`。
4. **`service.py`** — 看业务核心（最重），按两条线读：
   - **入库**：`ingest_file` → 解析（`extractors`）→ 切分（`chunk_text`）→ embedding → 保存（`complete_ingest_job`），每步记录 `KnowledgeIngestStep`。
   - **检索**：`search` → query embedding → pgvector 余弦检索 → `rerank_items` 精排 → 返回 topK。
5. **`extractors.py`** — 看文本抽取：PDF（PyMuPDF）/ 文本（多编码解码）。
6. **`db.py` + `security.py`** — 看基础设施：异步数据库连接和服务间认证。

> 关键点：knowledge-service 独立于主后端，有自己的数据库连接和配置。主后端通过 HTTP（`X-KB-Service-Token` 认证）访问它，两者不共享数据库访问代码。文档列表的关键词搜索不搜正文（`content_text`），正文语义检索由 `search`（pgvector）承担。
