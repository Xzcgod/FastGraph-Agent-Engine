# app/ — 主后端（control-plane）

本目录是整个平台的**主后端 / 控制面**：负责认证、平台 Agent 配置、普通用户 Agent 调用、knowledge-service 代理，以及 LangGraph Agent 运行时的编排。它不直接管理知识正文（由独立的 `services/knowledge_service` 负责）。

## 目录结构

| 子目录 / 文件 | 作用 |
|---|---|
| `main.py` | FastAPI 应用入口：加载配置、挂载中间件、注册路由、生命周期与健康检查 |
| `api/` | HTTP 路由层，对外暴露 REST API |
| `core/` | 核心横切模块：配置、日志、指标、限流、中间件、LangGraph 运行时、提示词 |
| `models/` | SQLModel 数据库表结构（ORM 模型） |
| `schemas/` | Pydantic 请求/响应契约（API 数据校验） |
| `services/` | 业务服务层：数据库、LLM、Agent 配置、knowledge-service 客户端 |
| `utils/` | 通用工具：JWT 认证、消息处理、数据净化 |

## 阅读理解路线

推荐按「请求生命周期」的顺序阅读，从外到内、从入口到核心：

1. **`main.py`** — 先看应用如何组装：中间件执行顺序、路由前缀、生命周期（建表）、健康检查。建立全局视图。
2. **`api/v1/`** — 看请求从哪里进来：`api.py` 是路由聚合中心，然后分别看 `auth`（认证）、`agents`（普通用户调用）、`admin`（平台管理）、`chatbot`（旧通用聊天）。
3. **`services/`** — 看业务逻辑：`llm.py`（模型路由）、`agent_config.py`（Agent 配置 + 运行时准备）、`database.py`（数据访问）、`knowledge_client.py`（知识库代理）。
4. **`core/langgraph/`** — 看 Agent 大脑：`graph.py` 的 `Chatbot` 状态图，以及 `tools/` 下的动态工具，理解「LLM 调用 + 工具循环 + 检查点」的核心机制。
5. **`models/` + `schemas/`** — 看数据层：`models/` 是数据库表，`schemas/` 是 API 契约，两者分离演进。
6. **`utils/` + `core/`（其余）** — 看支撑层：`utils/auth.py`（JWT）、`utils/graph.py`（消息处理）、`core/config.py`（配置）、`core/logging.py`、`core/metrics.py`、`core/limiter.py`、`core/middleware.py`。

> 如果时间有限，优先读 `main.py → api/v1/api.py → services/agent_config.py → core/langgraph/graph.py` 这四条主线，即可串起整个请求处理流程。
